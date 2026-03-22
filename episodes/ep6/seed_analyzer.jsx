import { useState, useCallback, useMemo, useRef, useEffect } from "react";

// --- UTILS ---
function parseCSV(text) {
  const lines = text.trim().split("\n");
  const headers = lines[0].split(",").map(h => h.trim().replace(/"/g, ""));
  return lines.slice(1).map(line => {
    const vals = [];
    let current = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      if (line[i] === '"') { inQuotes = !inQuotes; continue; }
      if (line[i] === ',' && !inQuotes) { vals.push(current.trim()); current = ""; continue; }
      current += line[i];
    }
    vals.push(current.trim());
    const obj = {};
    headers.forEach((h, i) => obj[h] = vals[i] || "");
    return obj;
  });
}

function parseTrades(rows) {
  return rows.map(r => ({
    entryDate: r["Entry Time"]?.slice(0, 10) || "",
    exitDate: r["Exit Time"]?.slice(0, 10) || "",
    entryPrice: parseFloat(r["Entry Price"]) || 0,
    exitPrice: parseFloat(r["Exit Price"]) || 0,
    qty: parseInt(r["Quantity"]) || 0,
    pnl: parseFloat(r["P&L"]) || 0,
    fees: parseFloat(r["Fees"]) || 0,
    isWin: r["IsWin"] === "1",
    mfe: parseFloat(r["MFE"]) || 0,
    mae: parseFloat(r["MAE"]) || 0,
  })).filter(t => t.entryDate && t.exitDate);
}

function buildBalanceCurve(trades, startCash = 100000) {
  let balance = startCash;
  const points = [{ date: trades[0]?.entryDate || "2011-01-01", balance }];
  for (const t of trades) {
    balance += t.pnl - t.fees;
    points.push({ date: t.exitDate, balance });
  }
  return points;
}

function daysBetween(a, b) {
  return Math.abs(new Date(a) - new Date(b)) / 86400000;
}

function fuzzyMatch(seedsData, windowDays = 10) {
  if (seedsData.length < 2) return { matched: [], unmatched: {} };
  
  // Collect all trades from all seeds
  const allTrades = [];
  seedsData.forEach((sd, si) => {
    sd.trades.forEach((t, ti) => {
      allTrades.push({ ...t, seedIdx: si, seedName: sd.name, tradeIdx: ti });
    });
  });

  // Group into clusters: trades within windowDays of each other
  const used = new Set();
  const clusters = [];
  
  // Sort all by entry date
  allTrades.sort((a, b) => a.entryDate.localeCompare(b.entryDate));
  
  for (let i = 0; i < allTrades.length; i++) {
    if (used.has(i)) continue;
    const cluster = [allTrades[i]];
    used.add(i);
    for (let j = i + 1; j < allTrades.length; j++) {
      if (used.has(j)) continue;
      if (allTrades[j].seedIdx === allTrades[i].seedIdx) continue;
      // Check if already have this seed in cluster
      if (cluster.some(c => c.seedIdx === allTrades[j].seedIdx)) continue;
      if (daysBetween(allTrades[i].entryDate, allTrades[j].entryDate) <= windowDays) {
        cluster.push(allTrades[j]);
        used.add(j);
      }
    }
    clusters.push(cluster);
  }

  const seedCount = seedsData.length;
  const matched = clusters.filter(c => c.length >= 2);
  
  // Unmatched = clusters with only 1 trade (unique to that seed)
  const unmatchedBySeed = {};
  seedsData.forEach((sd, i) => { unmatchedBySeed[sd.name] = []; });
  clusters.filter(c => c.length === 1).forEach(c => {
    unmatchedBySeed[c[0].seedName].push(c[0]);
  });

  return { matched, unmatched: unmatchedBySeed, clusters };
}

function pairwiseFuzzy(tradesA, tradesB, overlapThreshold = 0.5) {
  // Match trades by time overlap: if two trades share > threshold of the shorter trade's
  // duration in simultaneous market exposure, they're covering the same move.
  const toMs = (d) => new Date(d).getTime();
  const DAY = 86400000;

  const overlapDays = (a, b) => {
    const start = Math.max(toMs(a.entryDate), toMs(b.entryDate));
    const end = Math.min(toMs(a.exitDate), toMs(b.exitDate));
    return Math.max(0, (end - start) / DAY);
  };

  const duration = (t) => Math.max(1, (toMs(t.exitDate) - toMs(t.entryDate)) / DAY);

  const matched = [];
  const usedB = new Set();

  for (const a of tradesA) {
    let bestJ = null, bestOverlap = 0;
    for (let j = 0; j < tradesB.length; j++) {
      if (usedB.has(j)) continue;
      const olap = overlapDays(a, tradesB[j]);
      const shorter = Math.min(duration(a), duration(tradesB[j]));
      const ratio = olap / shorter;
      if (ratio > overlapThreshold && olap > bestOverlap) {
        bestOverlap = olap;
        bestJ = j;
      }
    }
    if (bestJ !== null) {
      const b = tradesB[bestJ];
      matched.push({
        a, b,
        entryGap: daysBetween(a.entryDate, b.entryDate),
        exitGap: daysBetween(a.exitDate, b.exitDate),
        overlapDays: bestOverlap,
        overlapRatio: bestOverlap / Math.min(duration(a), duration(b)),
      });
      usedB.add(bestJ);
    }
  }

  const aMatchedEntries = new Set(matched.map(m => m.a.entryDate));
  const bMatchedEntries = new Set(matched.map(m => m.b.entryDate));
  const aUnmatched = tradesA.filter(t => !aMatchedEntries.has(t.entryDate));
  const bUnmatched = tradesB.filter(t => !bMatchedEntries.has(t.entryDate));
  return { matched, aUnmatched, bUnmatched };
}

// --- COLORS ---
const SEED_COLORS = [
  "#E8553A", "#3B82F6", "#10B981", "#F59E0B",
  "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16",
  "#F97316", "#14B8A6", "#A855F7", "#FB7185"
];

const BG = "#0F1117";
const SURFACE = "#1A1D27";
const BORDER = "#2A2D3A";
const TEXT = "#E2E4E9";
const TEXT_DIM = "#7A7F8E";
const GREEN = "#10B981";
const RED = "#EF4444";

// --- CHART COMPONENT ---
function BalanceChart({ seedsData }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);
  const [dims, setDims] = useState({ w: 900, h: 380 });

  useEffect(() => {
    const measure = () => {
      if (containerRef.current) {
        setDims(d => ({ ...d, w: containerRef.current.offsetWidth }));
      }
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  const allCurves = useMemo(() => 
    seedsData.map(sd => buildBalanceCurve(sd.trades)),
    [seedsData]
  );

  const { minDate, maxDate, minVal, maxVal } = useMemo(() => {
    let minD = "9999", maxD = "0000", minV = Infinity, maxV = -Infinity;
    allCurves.forEach(c => c.forEach(p => {
      if (p.date < minD) minD = p.date;
      if (p.date > maxD) maxD = p.date;
      if (p.balance < minV) minV = p.balance;
      if (p.balance > maxV) maxV = p.balance;
    }));
    return { minDate: minD, maxDate: maxD, minVal: Math.min(0, minV), maxVal: maxV * 1.05 };
  }, [allCurves]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = dims.w, H = dims.h;
    const pad = { l: 80, r: 20, t: 20, b: 40 };
    const cw = W - pad.l - pad.r;
    const ch = H - pad.t - pad.b;
    
    canvas.width = W * 2;
    canvas.height = H * 2;
    ctx.scale(2, 2);
    ctx.clearRect(0, 0, W, H);

    const dateToX = (d) => pad.l + ((new Date(d) - new Date(minDate)) / (new Date(maxDate) - new Date(minDate))) * cw;
    const valToY = (v) => pad.t + ch - ((v - minVal) / (maxVal - minVal)) * ch;

    // Grid
    ctx.strokeStyle = BORDER;
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 5; i++) {
      const y = pad.t + (ch / 5) * i;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      const val = maxVal - ((maxVal - minVal) / 5) * i;
      ctx.fillStyle = TEXT_DIM;
      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.textAlign = "right";
      ctx.fillText(val >= 1000000 ? `$${(val/1000000).toFixed(1)}M` : val >= 1000 ? `$${(val/1000).toFixed(0)}K` : `$${val.toFixed(0)}`, pad.l - 8, y + 3);
    }

    // Year labels
    const startY = new Date(minDate).getFullYear();
    const endY = new Date(maxDate).getFullYear();
    ctx.fillStyle = TEXT_DIM;
    ctx.textAlign = "center";
    ctx.font = "10px 'JetBrains Mono', monospace";
    for (let y = startY; y <= endY; y += 2) {
      const x = dateToX(`${y}-01-01`);
      ctx.fillText(y, x, H - pad.b + 20);
      ctx.strokeStyle = "#1E2130";
      ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, H - pad.b); ctx.stroke();
    }

    // Draw curves
    allCurves.forEach((curve, i) => {
      ctx.strokeStyle = SEED_COLORS[i % SEED_COLORS.length];
      ctx.lineWidth = 1.8;
      ctx.globalAlpha = 0.85;
      ctx.beginPath();
      curve.forEach((p, j) => {
        const x = dateToX(p.date), y = valToY(p.balance);
        j === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.globalAlpha = 1;
    });
  }, [allCurves, minDate, maxDate, minVal, maxVal, dims]);

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height: dims.h, display: "block" }}
      />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8, paddingLeft: 80 }}>
        {seedsData.map((sd, i) => {
          const finalBal = allCurves[i]?.[allCurves[i].length - 1]?.balance || 0;
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: TEXT_DIM }}>
              <div style={{ width: 10, height: 10, borderRadius: 2, background: SEED_COLORS[i] }} />
              <span style={{ color: SEED_COLORS[i], fontWeight: 600 }}>{sd.name}</span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", color: TEXT }}>
                {finalBal >= 1e6 ? `$${(finalBal/1e6).toFixed(1)}M` : `$${(finalBal/1e3).toFixed(0)}K`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// --- FUZZY MATCH VIEW ---
function FuzzyMatchView({ seedsData, windowDays }) {
  const { matched, unmatched } = useMemo(() => fuzzyMatch(seedsData, windowDays), [seedsData, windowDays]);
  
  const seedNames = seedsData.map(s => s.name);
  
  // Stats
  const matchedCount = matched.length;
  const totalUnmatched = Object.values(unmatched).reduce((s, arr) => s + arr.length, 0);
  
  // Matched trade PnL comparison
  const matchedByCluster = matched.map(cluster => {
    const byDate = cluster[0].entryDate;
    const exitDates = cluster.map(c => c.exitDate);
    const exitGap = cluster.length >= 2 ? daysBetween(exitDates[0], exitDates[exitDates.length - 1]) : 0;
    const pnls = {};
    cluster.forEach(t => { pnls[t.seedName] = t.pnl; });
    const pnlVals = Object.values(pnls);
    const avgPnl = pnlVals.reduce((a, b) => a + b, 0) / pnlVals.length;
    const sameDir = cluster.every(t => t.isWin === cluster[0].isWin);
    return { entryDate: byDate, exitGap, pnls, avgPnl, sameDir, cluster };
  });

  // Unmatched impact
  const unmatchedImpact = {};
  Object.entries(unmatched).forEach(([name, trades]) => {
    const total = trades.reduce((s, t) => s + t.pnl, 0);
    const wins = trades.filter(t => t.isWin).length;
    unmatchedImpact[name] = { count: trades.length, total, wins, losses: trades.length - wins };
  });

  const matchedPnlBySeed = {};
  seedNames.forEach(n => { matchedPnlBySeed[n] = 0; });
  matchedByCluster.forEach(mc => {
    Object.entries(mc.pnls).forEach(([name, pnl]) => {
      matchedPnlBySeed[name] = (matchedPnlBySeed[name] || 0) + pnl;
    });
  });

  const sameDirCount = matchedByCluster.filter(m => m.sameDir).length;
  const avgExitGap = matchedByCluster.length > 0 
    ? matchedByCluster.reduce((s, m) => s + m.exitGap, 0) / matchedByCluster.length 
    : 0;

  const fmt = (v) => v >= 1e6 ? `$${(v/1e6).toFixed(2)}M` : v >= 1e3 ? `$${(v/1e3).toFixed(0)}K` : `$${v.toFixed(0)}`;
  const fmtSigned = (v) => (v >= 0 ? "+" : "") + fmt(v);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Summary stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
        {[
          { label: "Matched Clusters", value: matchedCount, sub: `±${windowDays}d window` },
          { label: "Unmatched Trades", value: totalUnmatched, sub: "unique to one seed" },
          { label: "Same W/L Direction", value: matchedCount > 0 ? `${Math.round(sameDirCount/matchedCount*100)}%` : "—", sub: `${sameDirCount}/${matchedCount}` },
          { label: "Avg Exit Gap", value: `${avgExitGap.toFixed(1)}d`, sub: "matched pairs" },
        ].map((s, i) => (
          <div key={i} style={{ background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8, padding: "12px 14px" }}>
            <div style={{ fontSize: 11, color: TEXT_DIM, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: TEXT, fontFamily: "'JetBrains Mono', monospace" }}>{s.value}</div>
            <div style={{ fontSize: 11, color: TEXT_DIM }}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Matched vs Unmatched P&L breakdown */}
      <div style={{ background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8, padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: TEXT, marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
          Matched vs Unmatched P&L by Seed
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${BORDER}` }}>
                <th style={{ textAlign: "left", padding: "6px 8px", color: TEXT_DIM, fontWeight: 500 }}>Seed</th>
                <th style={{ textAlign: "right", padding: "6px 8px", color: TEXT_DIM, fontWeight: 500 }}>Matched P&L</th>
                <th style={{ textAlign: "right", padding: "6px 8px", color: TEXT_DIM, fontWeight: 500 }}>Unmatched P&L</th>
                <th style={{ textAlign: "right", padding: "6px 8px", color: TEXT_DIM, fontWeight: 500 }}>Unmatched #</th>
                <th style={{ textAlign: "right", padding: "6px 8px", color: TEXT_DIM, fontWeight: 500 }}>Total P&L</th>
              </tr>
            </thead>
            <tbody>
              {seedNames.map((name, i) => {
                const mp = matchedPnlBySeed[name] || 0;
                const ui = unmatchedImpact[name] || { total: 0, count: 0 };
                const total = mp + ui.total;
                return (
                  <tr key={name} style={{ borderBottom: `1px solid ${BORDER}22` }}>
                    <td style={{ padding: "6px 8px" }}>
                      <span style={{ color: SEED_COLORS[i], fontWeight: 600 }}>{name}</span>
                    </td>
                    <td style={{ textAlign: "right", padding: "6px 8px", color: TEXT }}>{fmtSigned(mp)}</td>
                    <td style={{ textAlign: "right", padding: "6px 8px", color: ui.total >= 0 ? GREEN : RED }}>{fmtSigned(ui.total)}</td>
                    <td style={{ textAlign: "right", padding: "6px 8px", color: TEXT_DIM }}>{ui.count} ({ui.wins}W/{ui.losses}L)</td>
                    <td style={{ textAlign: "right", padding: "6px 8px", color: total >= 0 ? GREEN : RED, fontWeight: 600 }}>{fmtSigned(total)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Matched clusters detail */}
      <div style={{ background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8, padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: TEXT, marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
          Matched Trade Clusters ({matchedCount})
        </div>
        <div style={{ maxHeight: 350, overflowY: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${BORDER}`, position: "sticky", top: 0, background: SURFACE }}>
                <th style={{ textAlign: "left", padding: "5px 6px", color: TEXT_DIM }}>Entry ~</th>
                <th style={{ textAlign: "center", padding: "5px 6px", color: TEXT_DIM }}>Seeds</th>
                <th style={{ textAlign: "center", padding: "5px 6px", color: TEXT_DIM }}>Exit Gap</th>
                <th style={{ textAlign: "center", padding: "5px 6px", color: TEXT_DIM }}>Dir</th>
                {seedNames.map(n => (
                  <th key={n} style={{ textAlign: "right", padding: "5px 6px", color: TEXT_DIM }}>{n.slice(0, 8)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matchedByCluster.sort((a, b) => a.entryDate.localeCompare(b.entryDate)).map((mc, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${BORDER}11` }}>
                  <td style={{ padding: "4px 6px", color: TEXT }}>{mc.entryDate}</td>
                  <td style={{ textAlign: "center", padding: "4px 6px", color: TEXT_DIM }}>{mc.cluster.length}</td>
                  <td style={{ textAlign: "center", padding: "4px 6px", color: mc.exitGap <= 3 ? GREEN : mc.exitGap <= 7 ? "#F59E0B" : RED }}>{mc.exitGap.toFixed(0)}d</td>
                  <td style={{ textAlign: "center", padding: "4px 6px", color: mc.sameDir ? GREEN : RED }}>{mc.sameDir ? "✓" : "✗"}</td>
                  {seedNames.map((n, si) => {
                    const p = mc.pnls[n];
                    return (
                      <td key={n} style={{ textAlign: "right", padding: "4px 6px", color: p == null ? BORDER : p >= 0 ? GREEN : RED }}>
                        {p != null ? fmt(p) : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Unmatched (missed) trades detail */}
      <div style={{ background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8, padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: TEXT, marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
          Missed Trades — Unique to One Seed ({totalUnmatched})
        </div>
        <div style={{ maxHeight: 350, overflowY: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${BORDER}`, position: "sticky", top: 0, background: SURFACE }}>
                <th style={{ textAlign: "left", padding: "5px 6px", color: TEXT_DIM }}>Seed</th>
                <th style={{ textAlign: "left", padding: "5px 6px", color: TEXT_DIM }}>Entry</th>
                <th style={{ textAlign: "left", padding: "5px 6px", color: TEXT_DIM }}>Exit</th>
                <th style={{ textAlign: "right", padding: "5px 6px", color: TEXT_DIM }}>Days</th>
                <th style={{ textAlign: "right", padding: "5px 6px", color: TEXT_DIM }}>P&L</th>
                <th style={{ textAlign: "center", padding: "5px 6px", color: TEXT_DIM }}>W/L</th>
              </tr>
            </thead>
            <tbody>
              {seedNames.flatMap((name, si) =>
                (unmatched[name] || []).sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl)).map((t, ti) => (
                  <tr key={`${name}-${ti}`} style={{ borderBottom: `1px solid ${BORDER}11` }}>
                    <td style={{ padding: "4px 6px" }}><span style={{ color: SEED_COLORS[si], fontWeight: 600 }}>{name.slice(0, 10)}</span></td>
                    <td style={{ padding: "4px 6px", color: TEXT }}>{t.entryDate}</td>
                    <td style={{ padding: "4px 6px", color: TEXT_DIM }}>{t.exitDate}</td>
                    <td style={{ textAlign: "right", padding: "4px 6px", color: TEXT_DIM }}>{daysBetween(t.entryDate, t.exitDate).toFixed(0)}</td>
                    <td style={{ textAlign: "right", padding: "4px 6px", color: t.pnl >= 0 ? GREEN : RED, fontWeight: 600 }}>{fmtSigned(t.pnl)}</td>
                    <td style={{ textAlign: "center", padding: "4px 6px", color: t.isWin ? GREEN : RED }}>{t.isWin ? "W" : "L"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// --- TIMELINE VIEW ---
function TimelineView({ seedsData, seedAIdx, seedBIdx }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [filter, setFilter] = useState("both");
  const [overlap, setOverlap] = useState(0.5);
  const [zoom, setZoom] = useState(null);
  const [dragStart, setDragStart] = useState(null);
  const [dragCurrent, setDragCurrent] = useState(null);
  const [W, setW] = useState(920);
  const H = 340;
  const pad = { l: 20, r: 20, t: 50, b: 50 };

  // Measure container width
  useEffect(() => {
    const measure = () => {
      if (containerRef.current) {
        setW(containerRef.current.offsetWidth);
      }
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  const sdA = seedsData[seedAIdx];
  const sdB = seedsData[seedBIdx];

  // Reset zoom when seeds change
  useEffect(() => { setZoom(null); }, [seedAIdx, seedBIdx]);

  const { matched, aUnmatched, bUnmatched, fullDates, stats } = useMemo(() => {
    if (!sdA || !sdB) return { matched: [], aUnmatched: [], bUnmatched: [], fullDates: {}, stats: {} };
    const res = pairwiseFuzzy(sdA.trades, sdB.trades, overlap);
    const allT = [...sdA.trades, ...sdB.trades];
    const minD = allT.reduce((m, t) => t.entryDate < m ? t.entryDate : m, "9999");
    const maxD = allT.reduce((m, t) => t.exitDate > m ? t.exitDate : m, "0000");
    const pctOf = (t) => (t.exitPrice - t.entryPrice) / t.entryPrice * 100;
    const exit3 = res.matched.filter(m => m.exitGap <= 3).length;
    const sameDir = res.matched.filter(m => m.a.isWin === m.b.isWin).length;
    return {
      ...res,
      fullDates: { minMs: new Date(minD).getTime(), maxMs: new Date(maxD).getTime() },
      stats: {
        exit3, sameDir,
        matchedPnlA: res.matched.reduce((s, m) => s + pctOf(m.a), 0),
        matchedPnlB: res.matched.reduce((s, m) => s + pctOf(m.b), 0),
        unmatchedPnlA: res.aUnmatched.reduce((s, t) => s + pctOf(t), 0),
        unmatchedPnlB: res.bUnmatched.reduce((s, t) => s + pctOf(t), 0),
        totalA: sdA.trades.reduce((s, t) => s + pctOf(t), 0),
        totalB: sdB.trades.reduce((s, t) => s + pctOf(t), 0),
      }
    };
  }, [sdA, sdB, overlap]);

  const viewMinMs = zoom ? zoom.minMs : fullDates.minMs;
  const viewMaxMs = zoom ? zoom.maxMs : fullDates.maxMs;
  const cw = W - pad.l - pad.r;
  const dateToX = (d) => pad.l + ((new Date(d).getTime() - viewMinMs) / (viewMaxMs - viewMinMs)) * cw;
  const xToMs = (x) => viewMinMs + ((x - pad.l) / cw) * (viewMaxMs - viewMinMs);

  const getCanvasX = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    return (e.clientX - rect.left) * (W / rect.width);
  };

  const handleMouseDown = (e) => {
    const x = getCanvasX(e);
    if (x >= pad.l && x <= W - pad.r) { setDragStart(x); setDragCurrent(x); }
  };
  const handleMouseMove = (e) => {
    if (dragStart === null) return;
    setDragCurrent(Math.max(pad.l, Math.min(W - pad.r, getCanvasX(e))));
  };
  const handleMouseUp = () => {
    if (dragStart !== null && dragCurrent !== null && Math.abs(dragCurrent - dragStart) > 10) {
      const ms1 = xToMs(Math.min(dragStart, dragCurrent));
      const ms2 = xToMs(Math.max(dragStart, dragCurrent));
      setZoom({ minMs: ms1, maxMs: ms2 });
    }
    setDragStart(null); setDragCurrent(null);
  };
  const handleMouseLeave = () => { setDragStart(null); setDragCurrent(null); };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !sdA || !sdB || !viewMinMs || !viewMaxMs) return;
    const ctx = canvas.getContext("2d");
    canvas.width = W * 2; canvas.height = H * 2;
    ctx.scale(2, 2);
    ctx.clearRect(0, 0, W, H);

    const rowAY = pad.t + 30, rowBY = pad.t + 120, barH = 28;
    const colorA = SEED_COLORS[seedAIdx % SEED_COLORS.length];
    const colorB = SEED_COLORS[seedBIdx % SEED_COLORS.length];
    const showMatched = filter === "both" || filter === "matched";
    const showUnique = filter === "both" || filter === "unique";
    const dimMatched = filter === "unique";
    const dimUnique = filter === "matched";

    // Adaptive grid
    const spanYrs = (viewMaxMs - viewMinMs) / (365.25 * 86400000);
    const gridMo = spanYrs > 8 ? 24 : spanYrs > 4 ? 12 : spanYrs > 2 ? 6 : spanYrs > 1 ? 3 : 1;
    const moNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    const startY = new Date(viewMinMs).getFullYear();
    const endY = new Date(viewMaxMs).getFullYear() + 1;
    for (let y = startY; y <= endY; y++) {
      for (let mo = 0; mo < 12; mo += gridMo) {
        const ms = new Date(y, mo, 1).getTime();
        if (ms < viewMinMs || ms > viewMaxMs) continue;
        const x = pad.l + ((ms - viewMinMs) / (viewMaxMs - viewMinMs)) * cw;
        ctx.strokeStyle = "#1E2130"; ctx.lineWidth = 0.5;
        ctx.beginPath(); ctx.moveTo(x, pad.t + 10); ctx.lineTo(x, H - pad.b + 10); ctx.stroke();
        ctx.fillStyle = TEXT_DIM;
        const label = gridMo >= 12 ? `${y}` : gridMo >= 6 ? `${moNames[mo]} '${String(y).slice(2)}` : `${moNames[mo]} '${String(y).slice(2)}`;
        ctx.fillText(label, x, H - pad.b + 25);
      }
    }

    // Row labels
    ctx.font = "bold 11px 'JetBrains Mono', monospace"; ctx.textAlign = "left";
    ctx.fillStyle = colorA; ctx.fillText(sdA.name, pad.l, rowAY - 6);
    ctx.fillStyle = colorB; ctx.fillText(sdB.name, pad.l, rowBY - 6);

    // Connections
    if (showMatched && !dimMatched) {
      for (const m of matched) {
        const ax = (dateToX(m.a.entryDate) + dateToX(m.a.exitDate)) / 2;
        const bx = (dateToX(m.b.entryDate) + dateToX(m.b.exitDate)) / 2;
        ctx.strokeStyle = "#ffffff18"; ctx.lineWidth = 1; ctx.setLineDash([2, 4]);
        ctx.beginPath(); ctx.moveTo(ax, rowAY + barH); ctx.lineTo(bx, rowBY); ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // Clip to chart area
    ctx.save(); ctx.beginPath(); ctx.rect(pad.l, 0, cw, H); ctx.clip();

    // Matched bars
    if (showMatched) {
      const a = dimMatched ? "15" : "55", sa = dimMatched ? "10" : "40";
      for (const m of matched) {
        let x1 = dateToX(m.a.entryDate), w = Math.max(dateToX(m.a.exitDate) - x1, 3);
        ctx.fillStyle = colorA + a; ctx.fillRect(x1, rowAY, w, barH);
        ctx.strokeStyle = colorA + sa; ctx.lineWidth = 0.5; ctx.strokeRect(x1, rowAY, w, barH);
        x1 = dateToX(m.b.entryDate); w = Math.max(dateToX(m.b.exitDate) - x1, 3);
        ctx.fillStyle = colorB + a; ctx.fillRect(x1, rowBY, w, barH);
        ctx.strokeStyle = colorB + sa; ctx.strokeRect(x1, rowBY, w, barH);
      }
    }

    // Unique bars
    const drawUniq = (t, y, color, dim) => {
      const x1 = dateToX(t.entryDate), w = Math.max(dateToX(t.exitDate) - x1, 3);
      if (dim) { ctx.fillStyle = color + "10"; ctx.fillRect(x1, y, w, barH); return; }
      ctx.fillStyle = t.isWin ? "#10B981CC" : "#EF4444CC"; ctx.fillRect(x1, y, w, barH);
      ctx.strokeStyle = t.isWin ? "#10B981" : "#EF4444"; ctx.lineWidth = 1.5; ctx.strokeRect(x1, y, w, barH);
    };
    if (showUnique) {
      for (const t of aUnmatched) drawUniq(t, rowAY, colorA, dimUnique);
      for (const t of bUnmatched) drawUniq(t, rowBY, colorB, dimUnique);
    }

    ctx.restore();

    // Drag highlight
    if (dragStart !== null && dragCurrent !== null && Math.abs(dragCurrent - dragStart) > 5) {
      const sx = Math.min(dragStart, dragCurrent), sw = Math.abs(dragCurrent - dragStart);
      ctx.fillStyle = "#3B82F618"; ctx.fillRect(sx, pad.t, sw, H - pad.t - pad.b + 20);
      ctx.strokeStyle = "#3B82F6"; ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]); ctx.strokeRect(sx, pad.t, sw, H - pad.t - pad.b + 20); ctx.setLineDash([]);

      // Show date range being selected
      const d1 = new Date(xToMs(sx)), d2 = new Date(xToMs(sx + sw));
      const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
      ctx.font = "bold 10px 'JetBrains Mono', monospace"; ctx.textAlign = "center"; ctx.fillStyle = "#3B82F6";
      ctx.fillText(`${fmt(d1)} → ${fmt(d2)}`, sx + sw/2, pad.t - 4);
    }

    // Legend
    const legX = W - 280, legY = pad.t - 2;
    ctx.font = "10px 'JetBrains Mono', monospace"; ctx.textAlign = "left";
    ctx.fillStyle = colorA + "55"; ctx.fillRect(legX, legY - 8, 14, 10);
    ctx.fillStyle = TEXT_DIM; ctx.fillText("Matched", legX + 18, legY);
    ctx.fillStyle = "#10B981CC"; ctx.fillRect(legX + 80, legY - 8, 14, 10);
    ctx.fillStyle = TEXT_DIM; ctx.fillText("Unique W", legX + 98, legY);
    ctx.fillStyle = "#EF4444CC"; ctx.fillRect(legX + 165, legY - 8, 14, 10);
    ctx.fillStyle = TEXT_DIM; ctx.fillText("Unique L", legX + 183, legY);

  }, [sdA, sdB, matched, aUnmatched, bUnmatched, fullDates, seedAIdx, seedBIdx, filter, stats, zoom, dragStart, dragCurrent, viewMinMs, viewMaxMs]);

  if (!sdA || !sdB) return null;
  const fmt = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(0)}%`;
  const totalGap = stats.totalA - stats.totalB;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Controls row */}
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 2, background: SURFACE, borderRadius: 6, padding: 2 }}>
          {[
            { id: "both", label: "All Trades" },
            { id: "matched", label: "Matched Only" },
            { id: "unique", label: "Unique Only" },
          ].map(f => (
            <button key={f.id} onClick={() => setFilter(f.id)} style={{
              background: filter === f.id ? (f.id === "unique" ? "#F59E0B" : f.id === "matched" ? "#3B82F6" : BORDER) : "transparent",
              color: filter === f.id ? (f.id === "both" ? TEXT : "#fff") : TEXT_DIM,
              border: "none", borderRadius: 4, padding: "5px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer",
            }}>{f.label}</button>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, color: TEXT_DIM }}>Overlap:</span>
          {[0.3, 0.5, 0.7].map(o => (
            <button key={o} onClick={() => setOverlap(o)} style={{
              background: overlap === o ? BORDER : "transparent", color: overlap === o ? TEXT : TEXT_DIM,
              border: `1px solid ${overlap === o ? TEXT_DIM : "transparent"}`, borderRadius: 4, padding: "3px 8px", fontSize: 11, cursor: "pointer",
            }}>{o * 100}%</button>
          ))}
        </div>
        {zoom && (
          <button onClick={() => setZoom(null)} style={{
            background: "#EF444422", color: "#EF4444", border: `1px solid #EF444444`,
            borderRadius: 4, padding: "4px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer",
          }}>Reset Zoom</button>
        )}
        {!zoom && (
          <span style={{ fontSize: 10, color: TEXT_DIM, fontStyle: "italic" }}>Click and drag to zoom in</span>
        )}
      </div>

      <div ref={containerRef} style={{ width: "100%" }}>
        <canvas ref={canvasRef}
          onMouseDown={handleMouseDown} onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp} onMouseLeave={handleMouseLeave}
          style={{ width: "100%", height: H, display: "block", background: SURFACE, borderRadius: 8,
                   border: `1px solid ${zoom ? '#3B82F644' : BORDER}`, cursor: dragStart ? "col-resize" : "crosshair" }} />
      </div>

      {/* Stats cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
        <div style={{ background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8, padding: "12px 14px" }}>
          <div style={{ fontSize: 11, color: TEXT_DIM, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>Matched Trades</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: TEXT, fontFamily: "'JetBrains Mono', monospace" }}>{matched.length}</div>
          <div style={{ fontSize: 11, color: TEXT_DIM }}>
            Exit ≤3d: {stats.exit3}/{matched.length} ({matched.length > 0 ? Math.round(stats.exit3/matched.length*100) : 0}%)
            {" · "}Same dir: {stats.sameDir}/{matched.length} ({matched.length > 0 ? Math.round(stats.sameDir/matched.length*100) : 0}%)
          </div>
        </div>
        <div style={{ background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8, padding: "12px 14px" }}>
          <div style={{ fontSize: 11, color: TEXT_DIM, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>Matched P&L</div>
          <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
            <span style={{ fontSize: 16, fontWeight: 700, color: SEED_COLORS[seedAIdx], fontFamily: "'JetBrains Mono', monospace" }}>{fmt(stats.matchedPnlA)}</span>
            <span style={{ fontSize: 11, color: TEXT_DIM }}>vs</span>
            <span style={{ fontSize: 16, fontWeight: 700, color: SEED_COLORS[seedBIdx], fontFamily: "'JetBrains Mono', monospace" }}>{fmt(stats.matchedPnlB)}</span>
          </div>
          <div style={{ fontSize: 11, color: TEXT_DIM }}>Delta: {fmt(stats.matchedPnlA - stats.matchedPnlB)}</div>
        </div>
        <div style={{ background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8, padding: "12px 14px" }}>
          <div style={{ fontSize: 11, color: TEXT_DIM, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>Unmatched P&L</div>
          <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
            <span style={{ fontSize: 16, fontWeight: 700, color: SEED_COLORS[seedAIdx], fontFamily: "'JetBrains Mono', monospace" }}>{fmt(stats.unmatchedPnlA)}</span>
            <span style={{ fontSize: 11, color: TEXT_DIM }}>vs</span>
            <span style={{ fontSize: 16, fontWeight: 700, color: SEED_COLORS[seedBIdx], fontFamily: "'JetBrains Mono', monospace" }}>{fmt(stats.unmatchedPnlB)}</span>
          </div>
          <div style={{ fontSize: 11, color: TEXT_DIM }}>{aUnmatched.length}t vs {bUnmatched.length}t · Gap: {fmt(stats.unmatchedPnlA - stats.unmatchedPnlB)}</div>
        </div>
      </div>

      {/* Gap decomposition bar */}
      {Math.abs(totalGap) > 1 && (() => {
        const matchedGap = stats.matchedPnlA - stats.matchedPnlB;
        const unmatchedGap = stats.unmatchedPnlA - stats.unmatchedPnlB;
        const mPct = Math.abs(totalGap) > 0 ? Math.abs(matchedGap / totalGap * 100) : 0;
        const uPct = Math.abs(totalGap) > 0 ? Math.abs(unmatchedGap / totalGap * 100) : 0;
        return (
          <div style={{ background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8, padding: "12px 14px" }}>
            <div style={{ fontSize: 11, color: TEXT_DIM, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
              Total gap: {fmt(totalGap)} — Where does it come from?
            </div>
            <div style={{ display: "flex", gap: 4, alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontSize: 10, color: TEXT_DIM, width: 70 }}>Matched</span>
              <div style={{ flex: 1, height: 16, background: BORDER, borderRadius: 3, overflow: "hidden" }}>
                <div style={{ width: `${Math.min(mPct, 100)}%`, height: "100%", background: "#3B82F6", borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: 11, color: TEXT, fontFamily: "'JetBrains Mono', monospace", width: 50, textAlign: "right" }}>{mPct.toFixed(0)}%</span>
            </div>
            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <span style={{ fontSize: 10, color: TEXT_DIM, width: 70 }}>Unmatched</span>
              <div style={{ flex: 1, height: 16, background: BORDER, borderRadius: 3, overflow: "hidden" }}>
                <div style={{ width: `${Math.min(uPct, 100)}%`, height: "100%", background: "#F59E0B", borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: 11, color: TEXT, fontFamily: "'JetBrains Mono', monospace", width: 50, textAlign: "right" }}>{uPct.toFixed(0)}%</span>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

// --- YEARLY RANKING HEATMAP ---
function YearlyRanking({ seedsData, showMode }) {
  const { yearly, years, seedNames, seedTotals } = useMemo(() => {
    const yMap = {};
    const ySet = new Set();
    const names = seedsData.map(s => s.name);
    const totals = {};

    seedsData.forEach((sd) => {
      yMap[sd.name] = {};
      totals[sd.name] = 0;
      for (const t of sd.trades) {
        const yr = parseInt(t.exitDate.slice(0, 4));
        if (isNaN(yr)) continue;
        ySet.add(yr);
        const pct = (t.exitPrice - t.entryPrice) / t.entryPrice * 100;
        yMap[sd.name][yr] = (yMap[sd.name][yr] || 0) + pct;
        totals[sd.name] += pct;
      }
    });

    return {
      yearly: yMap,
      years: [...ySet].sort(),
      seedNames: names,
      seedTotals: totals,
    };
  }, [seedsData]);

  // Compute ranks per year
  const ranks = useMemo(() => {
    const r = {};
    for (const yr of years) {
      const vals = seedNames.map(n => ({ name: n, val: yearly[n]?.[yr] || 0 }));
      vals.sort((a, b) => b.val - a.val);
      r[yr] = {};
      vals.forEach((v, i) => { r[yr][v.name] = i + 1; });
    }
    // Total rank
    const totalVals = seedNames.map(n => ({ name: n, val: seedTotals[n] || 0 }));
    totalVals.sort((a, b) => b.val - a.val);
    r["TOTAL"] = {};
    totalVals.forEach((v, i) => { r["TOTAL"][v.name] = i + 1; });
    return r;
  }, [yearly, years, seedNames, seedTotals]);

  // Sort seeds by total rank
  const sortedSeeds = useMemo(() => {
    return [...seedNames].sort((a, b) => (ranks["TOTAL"]?.[a] || 99) - (ranks["TOTAL"]?.[b] || 99));
  }, [seedNames, ranks]);

  const n = seedNames.length;

  const rankColor = (rank) => {
    if (n < 2) return SURFACE;
    const pct = (rank - 1) / (n - 1); // 0 = best, 1 = worst
    if (pct <= 0.2) return "#064E3B"; // deep green
    if (pct <= 0.35) return "#065F46";
    if (pct <= 0.5) return "#1A3A2A";
    if (pct <= 0.65) return "#2A2520";
    if (pct <= 0.8) return "#4A1E1E";
    return "#7F1D1D"; // deep red
  };

  const rankTextColor = (rank) => {
    if (n < 2) return TEXT;
    const pct = (rank - 1) / (n - 1);
    if (pct <= 0.2) return "#6EE7B7";
    if (pct <= 0.35) return "#A7F3D0";
    if (pct <= 0.65) return TEXT_DIM;
    if (pct <= 0.8) return "#FCA5A5";
    return "#FCA5A5";
  };

  const showRank = showMode === "rank";

  return (
    <div style={{ background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8, padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: TEXT, textTransform: "uppercase", letterSpacing: 1 }}>
          Yearly {showRank ? "Rankings" : "Returns"} Heatmap
        </div>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", fontSize: 11, fontFamily: "'JetBrains Mono', monospace", width: "100%" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "5px 8px", color: TEXT_DIM, fontWeight: 500, position: "sticky", left: 0, background: SURFACE, zIndex: 1 }}>Seed</th>
              {years.map(yr => (
                <th key={yr} style={{ textAlign: "center", padding: "5px 4px", color: TEXT_DIM, fontWeight: 500, minWidth: 38 }}>{String(yr).slice(2)}</th>
              ))}
              <th style={{ textAlign: "center", padding: "5px 8px", color: TEXT, fontWeight: 700, borderLeft: `2px solid ${BORDER}`, minWidth: 50 }}>Total</th>
            </tr>
          </thead>
          <tbody>
            {sortedSeeds.map((name, si) => {
              const seedIdx = seedsData.findIndex(s => s.name === name);
              const totalRank = ranks["TOTAL"]?.[name] || 0;
              const totalPct = seedTotals[name] || 0;
              return (
                <tr key={name}>
                  <td style={{
                    padding: "4px 8px", position: "sticky", left: 0, background: SURFACE, zIndex: 1,
                    borderRight: `1px solid ${BORDER}`,
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <div style={{ width: 7, height: 7, borderRadius: 2, background: SEED_COLORS[seedIdx % SEED_COLORS.length], flexShrink: 0 }} />
                      <span style={{ color: TEXT, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 90 }}>{name}</span>
                    </div>
                  </td>
                  {years.map(yr => {
                    const rank = ranks[yr]?.[name] || 0;
                    const val = yearly[name]?.[yr] || 0;
                    return (
                      <td key={yr} style={{
                        textAlign: "center", padding: "4px 2px",
                        background: rankColor(rank),
                        color: showRank ? rankTextColor(rank) : (val >= 0 ? GREEN : RED),
                        fontWeight: (showRank && (rank === 1 || rank === n)) ? 700 : 400,
                        borderRadius: 2,
                      }}>
                        {showRank ? `#${rank}` : `${val >= 0 ? "+" : ""}${val.toFixed(0)}%`}
                      </td>
                    );
                  })}
                  <td style={{
                    textAlign: "center", padding: "4px 8px",
                    background: rankColor(totalRank),
                    color: showRank ? rankTextColor(totalRank) : (totalPct >= 0 ? GREEN : RED),
                    fontWeight: 700,
                    borderLeft: `2px solid ${BORDER}`,
                  }}>
                    {showRank ? `#${totalRank}` : `${totalPct >= 0 ? "+" : ""}${totalPct.toFixed(0)}%`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {/* Stats row */}
      <div style={{ marginTop: 12, display: "flex", gap: 16, fontSize: 11, color: TEXT_DIM }}>
        {(() => {
          // Count top3/bot3 per seed
          const stats = sortedSeeds.map(name => {
            let top3 = 0, bot3 = 0;
            years.forEach(yr => {
              const rank = ranks[yr]?.[name] || 0;
              if (rank <= 3) top3++;
              if (rank >= n - 2) bot3++;
            });
            return { name, top3, bot3 };
          });
          const best = stats.reduce((a, b) => a.top3 > b.top3 ? a : b);
          const mostConsistent = stats.reduce((a, b) => a.bot3 < b.bot3 ? a : b);
          return (
            <>
              <span>Most top-3 finishes: <span style={{ color: TEXT, fontWeight: 600 }}>{best.name}</span> ({best.top3}/{years.length})</span>
              <span>Fewest bottom-3: <span style={{ color: TEXT, fontWeight: 600 }}>{mostConsistent.name}</span> ({mostConsistent.bot3}/{years.length})</span>
            </>
          );
        })()}
      </div>
    </div>
  );
}

// --- MAIN APP ---
export default function App() {
  const [seeds, setSeeds] = useState([]);
  const [windowDays, setWindowDays] = useState(10);
  const [activeTab, setActiveTab] = useState("chart");
  const [rankMode, setRankMode] = useState("rank");
  const [tlSeedA, setTlSeedA] = useState(0);
  const [tlSeedB, setTlSeedB] = useState(1);
  const fileInputRef = useRef(null);

  const handleFiles = useCallback(async (e) => {
    const files = Array.from(e.target.files);
    const newSeeds = [];
    for (const f of files) {
      const text = await f.text();
      const rows = parseCSV(text);
      const trades = parseTrades(rows);
      const name = f.name.replace(/_trades\.csv$/i, "").replace(/_/g, " ").replace(/\.csv$/i, "");
      newSeeds.push({ name, trades, fileName: f.name });
    }
    setSeeds(prev => [...prev, ...newSeeds].slice(0, 12));
    e.target.value = "";
  }, []);

  const removeSeed = (i) => setSeeds(prev => prev.filter((_, j) => j !== i));
  const clearAll = () => setSeeds([]);

  return (
    <div style={{
      background: BG,
      color: TEXT,
      minHeight: "100vh",
      fontFamily: "'DM Sans', 'Segoe UI', sans-serif",
      padding: "20px 24px",
    }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 11, color: TEXT_DIM, textTransform: "uppercase", letterSpacing: 2, marginBottom: 4 }}>
          Prompt to Profit · EP6 Analysis
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, color: TEXT, letterSpacing: -0.5 }}>
          Seed Path Dependency Analyzer
        </h1>
      </div>

      {/* Upload area */}
      <div style={{
        background: SURFACE,
        border: `1px dashed ${seeds.length >= 12 ? BORDER : "#3B82F6"}`,
        borderRadius: 10,
        padding: "16px 20px",
        marginBottom: 16,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 10,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={seeds.length >= 12}
            style={{
              background: seeds.length >= 12 ? BORDER : "#3B82F6",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              padding: "8px 16px",
              fontWeight: 600,
              fontSize: 13,
              cursor: seeds.length >= 12 ? "default" : "pointer",
              opacity: seeds.length >= 12 ? 0.5 : 1,
            }}
          >
            Upload Trade CSVs
          </button>
          <input ref={fileInputRef} type="file" accept=".csv" multiple onChange={handleFiles} style={{ display: "none" }} />
          <span style={{ fontSize: 12, color: TEXT_DIM }}>{seeds.length}/12 seeds loaded</span>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {seeds.map((s, i) => (
            <div key={i} style={{
              background: BG,
              border: `1px solid ${SEED_COLORS[i]}44`,
              borderRadius: 5,
              padding: "3px 8px",
              fontSize: 11,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}>
              <div style={{ width: 7, height: 7, borderRadius: 2, background: SEED_COLORS[i] }} />
              <span style={{ color: TEXT, maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
              <span style={{ color: TEXT_DIM }}>{s.trades.length}t</span>
              <span onClick={() => removeSeed(i)} style={{ color: TEXT_DIM, cursor: "pointer", fontWeight: 700, fontSize: 13 }}>×</span>
            </div>
          ))}
          {seeds.length > 0 && (
            <button onClick={clearAll} style={{
              background: "transparent", border: `1px solid ${BORDER}`, borderRadius: 5,
              padding: "3px 8px", fontSize: 11, color: TEXT_DIM, cursor: "pointer"
            }}>Clear all</button>
          )}
        </div>
      </div>

      {seeds.length === 0 ? (
        <div style={{
          background: SURFACE, borderRadius: 10, padding: "60px 20px",
          textAlign: "center", border: `1px solid ${BORDER}`
        }}>
          <div style={{ fontSize: 36, marginBottom: 8 }}>📊</div>
          <div style={{ fontSize: 15, color: TEXT, fontWeight: 600, marginBottom: 4 }}>Upload trade history CSVs</div>
          <div style={{ fontSize: 12, color: TEXT_DIM }}>
            QuantConnect format with Entry Time, Exit Time, P&L columns. Up to 8 seed files.
          </div>
        </div>
      ) : (
        <>
          {/* Tabs */}
          <div style={{ display: "flex", gap: 2, marginBottom: 16, background: SURFACE, borderRadius: 8, padding: 3, width: "fit-content" }}>
            {[
              { id: "chart", label: "Balance Curves" },
              { id: "ranking", label: "Yearly Rankings" },
              { id: "timeline", label: "Timeline" },
              { id: "fuzzy", label: "Fuzzy Match" },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  background: activeTab === tab.id ? "#3B82F6" : "transparent",
                  color: activeTab === tab.id ? "#fff" : TEXT_DIM,
                  border: "none",
                  borderRadius: 6,
                  padding: "7px 16px",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {tab.label}
              </button>
            ))}
            {activeTab === "ranking" && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: 12 }}>
                {["rank", "pct"].map(m => (
                  <button
                    key={m}
                    onClick={() => setRankMode(m)}
                    style={{
                      background: rankMode === m ? BORDER : "transparent",
                      color: rankMode === m ? TEXT : TEXT_DIM,
                      border: `1px solid ${rankMode === m ? TEXT_DIM : "transparent"}`,
                      borderRadius: 4, padding: "3px 8px", fontSize: 11, cursor: "pointer",
                    }}
                  >
                    {m === "rank" ? "Rank #" : "Return %"}
                  </button>
                ))}
              </div>
            )}
            {activeTab === "timeline" && seeds.length >= 2 && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: 12 }}>
                <select value={tlSeedA} onChange={e => setTlSeedA(Number(e.target.value))}
                  style={{ background: BORDER, color: TEXT, border: "none", borderRadius: 4, padding: "3px 6px", fontSize: 11 }}>
                  {seeds.map((s, i) => <option key={i} value={i}>{s.name}</option>)}
                </select>
                <span style={{ fontSize: 11, color: TEXT_DIM }}>vs</span>
                <select value={tlSeedB} onChange={e => setTlSeedB(Number(e.target.value))}
                  style={{ background: BORDER, color: TEXT, border: "none", borderRadius: 4, padding: "3px 6px", fontSize: 11 }}>
                  {seeds.map((s, i) => <option key={i} value={i}>{s.name}</option>)}
                </select>
              </div>
            )}
            {activeTab === "fuzzy" && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: 12 }}>
                <span style={{ fontSize: 11, color: TEXT_DIM }}>Window:</span>
                {[5, 10, 15, 20].map(d => (
                  <button
                    key={d}
                    onClick={() => setWindowDays(d)}
                    style={{
                      background: windowDays === d ? BORDER : "transparent",
                      color: windowDays === d ? TEXT : TEXT_DIM,
                      border: `1px solid ${windowDays === d ? TEXT_DIM : "transparent"}`,
                      borderRadius: 4, padding: "3px 8px", fontSize: 11, cursor: "pointer",
                    }}
                  >
                    ±{d}d
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Content */}
          {activeTab === "chart" && <BalanceChart seedsData={seeds} />}
          {activeTab === "ranking" && <YearlyRanking seedsData={seeds} showMode={rankMode} />}
          {activeTab === "timeline" && seeds.length >= 2 && <TimelineView seedsData={seeds} seedAIdx={tlSeedA} seedBIdx={tlSeedB} />}
          {activeTab === "timeline" && seeds.length < 2 && (
            <div style={{ background: SURFACE, borderRadius: 10, padding: "40px 20px", textAlign: "center", border: `1px solid ${BORDER}` }}>
              <div style={{ fontSize: 13, color: TEXT_DIM }}>Upload at least 2 seed files to view timeline</div>
            </div>
          )}
          {activeTab === "fuzzy" && seeds.length >= 2 && <FuzzyMatchView seedsData={seeds} windowDays={windowDays} />}
          {activeTab === "fuzzy" && seeds.length < 2 && (
            <div style={{ background: SURFACE, borderRadius: 10, padding: "40px 20px", textAlign: "center", border: `1px solid ${BORDER}` }}>
              <div style={{ fontSize: 13, color: TEXT_DIM }}>Upload at least 2 seed files to run fuzzy matching</div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
