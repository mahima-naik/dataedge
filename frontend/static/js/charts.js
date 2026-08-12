let chartTimeline = null;
let chartPie = null;
let chartConversion = null;
let chartProgress = null;
let chartWeekday = null;
let chartHourly = null;
let sparkCharts = {};

let _lastChartUpdateTime = 0;
const CHART_UPDATE_THROTTLE_MS = 3000;

const CHART_COLORS = ['#DC2626', '#16A34A', '#D97706', '#9333EA', '#DB2777', '#EA580C', '#0891B2', '#65A30D'];
const CHART_WEEKDAY_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function coerceNumArray7(raw) {
  if (!Array.isArray(raw)) return [];
  return raw.map(function (x) { var n = Number(x); return Number.isFinite(n) ? n : 0; });
}

function formatTimelineAxisLabel(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(String(iso).trim())) return String(iso || '');
  var t = String(iso).trim();
  var ms = Date.parse(t + 'T06:30:00.000Z');
  if (isNaN(ms)) return t;
  return new Date(ms).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', weekday: 'short', day: 'numeric', month: 'short' });
}

function getLastSevenPlaceholderCategories() {
  var labels = [], now = new Date();
  for (var i = 0; i < 7; i++) {
    var ms = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - (6 - i));
    labels.push(CHART_WEEKDAY_SHORT[new Date(ms).getUTCDay()]);
  }
  return labels;
}

function getLast7DaysUtc() {
  var out = [], now = new Date(), i;
  for (i = 0; i < 7; i++) {
    var ms = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - (6 - i));
    out.push(CHART_WEEKDAY_SHORT[new Date(ms).getUTCDay()]);
  }
  return out;
}

function leadTimelineMs(lead) {
  if (!lead || typeof lead !== 'object') return NaN;
  var st = lead.start_time;
  if (st != null && Number(st) > 0) return Number(st) * 1000;
  var iso = lead.called_at_iso;
  if (!iso) return NaN;
  try {
    var s = String(iso);
    var hasTZ = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(s);
    if (!hasTZ && /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s)) s = s + 'Z';
    var t = Date.parse(s);
    return isNaN(t) ? NaN : t;
  } catch (_) { return NaN; }
}

function weekdayShortUtc(ms) { return CHART_WEEKDAY_SHORT[new Date(ms).getUTCDay()]; }

function getHourFromLead(lead) {
  var ms = leadTimelineMs(lead);
  if (isNaN(ms)) return -1;
  return new Date(ms).getHours();
}

function getRating(lead) {
  if (!lead || !lead.analysis) return null;
  var r = parseInt(lead.analysis.rating, 10);
  return Number.isFinite(r) && r >= 1 && r <= 5 ? r : null;
}

function initCharts() {
  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  var c = isDark
    ? { text: '#9C9CA0', bg: '#0D0D0D', border: '#1A1A1A' }
    : { text: '#6C6C70', bg: '#FFFFFF', border: '#E5E5E7' };
  var RED = '#DC2626', RED_LIGHT = isDark ? 'rgba(220,38,38,0.15)' : 'rgba(220,38,38,0.08)', GREEN = '#16A34A', ORANGE = '#EA580C', AMBER = '#D97706', GRAY = '#9CA3AF', PURPLE = '#9333EA';

  // Engagement Timeline
  var timelineEl = document.getElementById('chart-timeline');
  if (timelineEl) {
    chartTimeline = new ApexCharts(timelineEl, {
      series: [
        { name: 'Total Calls', data: Array(7).fill(0) },
        { name: 'Interested', data: Array(7).fill(0) },
        { name: 'Inbound', data: Array(7).fill(0) },
      ],
      chart: { type: 'area', height: 220, toolbar: { show: false }, background: 'transparent', fontFamily: 'inherit' },
      colors: [GRAY, GREEN, RED],
      fill: { type: 'solid', opacity: [0.08, 0.08, 0.08] },
      stroke: { curve: 'smooth', width: [2, 2, 2] },
      markers: { size: [3, 3, 3], strokeWidth: 1.5, hover: { sizeOffset: 2 } },
      xaxis: { categories: getLastSevenPlaceholderCategories(), labels: { style: { colors: Array(7).fill(c.text), fontSize: '10px' } } },
      yaxis: { min: 0, labels: { style: { colors: [c.text], fontSize: '9px' } } },
      grid: { borderColor: c.border, strokeDashArray: 4 },
      legend: { show: false },
      tooltip: { shared: true, intersect: false, theme: 'light' },
      dataLabels: { enabled: false },
    });
    chartTimeline.render();
  }

  // Outcome Distribution
  var pieEl = document.getElementById('chart-pie');
  if (pieEl) {
    chartPie = new ApexCharts(pieEl, {
      series: [0, 0, 0, 0, 0],
      chart: { type: 'donut', height: 220, background: 'transparent', fontFamily: 'inherit' },
      labels: ['Interested', 'Not Interested', 'Call Later', 'Failed', 'Answered'],
      colors: [GREEN, RED, '#3B82F6', ORANGE, GRAY],
      legend: { position: 'bottom', labels: { colors: Array(5).fill(c.text) }, fontSize: '10px', itemMargin: { horizontal: 8 } },
      dataLabels: { enabled: false },
      stroke: { show: false },
      plotOptions: { pie: { donut: { size: '60%', labels: { show: true, name: { show: false }, value: { show: true, fontSize: '20px', fontWeight: 700, color: isDark ? '#E5E5E7' : '#1C1C1E', offsetY: 2 }, total: { show: true, showAlways: true, label: 'Total', fontSize: '10px', fontWeight: 600, color: c.text, formatter: function () { return '0'; } } } } } },
    });
    chartPie.render();
  }

  // Conversion Gauge
  var convEl = document.getElementById('chart-conversion');
  if (convEl) {
    chartConversion = new ApexCharts(convEl, {
      series: [0],
      chart: { type: 'radialBar', height: 220, background: 'transparent', fontFamily: 'inherit' },
      colors: [RED],
      plotOptions: {
        radialBar: {
          hollow: { size: '60%' },
          track: { background: c.border, strokeWidth: '100%' },
          dataLabels: {
            show: true,
            name: { show: true, fontSize: '11px', fontWeight: 600, color: c.text, offsetY: -8, formatter: function () { return 'Conversion'; } },
            value: { show: true, fontSize: '24px', fontWeight: 800, color: isDark ? '#E5E5E7' : '#1C1C1E', offsetY: 2, formatter: function (v) { return v.toFixed(1) + '%'; } },
          },
        },
      },
      stroke: { lineCap: 'round' },
      labels: ['Conversion Rate'],
    });
    chartConversion.render();
  }

  // Campaign Progress (horizontal stacked bar)
  var progressEl = document.getElementById('chart-progress');
  if (progressEl) {
    chartProgress = new ApexCharts(progressEl, {
      series: [
        { name: 'Connected', data: [0] },
        { name: 'Failed', data: [0] },
        { name: 'No Answer', data: [0] },
        { name: 'Pending', data: [0] },
      ],
      chart: { type: 'bar', height: 200, stacked: true, stackType: '100%', background: 'transparent', fontFamily: 'inherit', toolbar: { show: false } },
      colors: ['#16A34A', RED, '#D97706', '#9CA3AF'],
      plotOptions: { bar: { borderRadius: 4, horizontal: true, barHeight: '60%' } },
      xaxis: { categories: ['Campaign'], labels: { show: false } },
      yaxis: { show: false },
      grid: { show: false },
      legend: { position: 'bottom', fontSize: '10px', labels: { colors: [c.text, c.text, c.text, c.text] }, itemMargin: { horizontal: 6 } },
      tooltip: { theme: 'light', y: { formatter: function (v) { return v + ' calls'; } } },
      dataLabels: { enabled: false },
    });
    chartProgress.render();
  }

  // Day of Week Distribution
  var weekdayEl = document.getElementById('chart-weekday');
  if (weekdayEl) {
    chartWeekday = new ApexCharts(weekdayEl, {
      series: [{ name: 'Calls', data: [0, 0, 0, 0, 0, 0, 0] }],
      chart: { type: 'bar', height: 200, background: 'transparent', fontFamily: 'inherit', toolbar: { show: false } },
      colors: [RED],
      plotOptions: { bar: { borderRadius: 3, columnWidth: '60%', distributed: false } },
      xaxis: {
        categories: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        labels: { style: { colors: Array(7).fill(c.text), fontSize: '10px' }, rotate: 0 },
      },
      yaxis: { min: 0, labels: { style: { colors: [c.text], fontSize: '9px' } } },
      grid: { borderColor: c.border, strokeDashArray: 4 },
      legend: { show: false },
      tooltip: { theme: 'light' },
      dataLabels: { enabled: false },
    });
    chartWeekday.render();
  }

  // Hourly Distribution
  var hourlyEl = document.getElementById('chart-hourly');
  if (hourlyEl) {
    chartHourly = new ApexCharts(hourlyEl, {
      series: [{ name: 'Calls', data: Array(24).fill(0) }],
      chart: { type: 'bar', height: 200, background: 'transparent', fontFamily: 'inherit', toolbar: { show: false } },
      colors: ['#0891B2'],
      plotOptions: { bar: { borderRadius: 2, columnWidth: '70%', distributed: false } },
      xaxis: {
        categories: ['12A','1A','2A','3A','4A','5A','6A','7A','8A','9A','10A','11A','12P','1P','2P','3P','4P','5P','6P','7P','8P','9P','10P','11P'],
        labels: { style: { colors: Array(24).fill(c.text), fontSize: '9px' }, rotate: 0, trim: false },
      },
      yaxis: { min: 0, labels: { style: { colors: [c.text], fontSize: '9px' }, formatter: val => Math.floor(val) } },
      grid: { borderColor: c.border, strokeDashArray: 4 },
      legend: { show: false },
      tooltip: { theme: 'light' },
      dataLabels: { enabled: false },
    });
    chartHourly.render();
  }
}

function updateCharts(leads, dispositionCounts, callbackCountsByDate, serverTimeline, chartExtras) {
  var now = Date.now();
  if (now - _lastChartUpdateTime < CHART_UPDATE_THROTTLE_MS) return;
  _lastChartUpdateTime = now;

  var st = serverTimeline && typeof serverTimeline === 'object' ? serverTimeline : {};
  var extras = chartExtras && typeof chartExtras === 'object' ? chartExtras : {};
  var dc = dispositionCounts || {};
  var list = Array.isArray(leads) ? leads : [];

  var interested = Number(dc['Interested'] || 0);
  var notInterested = Number(dc['Not Interested'] || 0);
  var callLaterPie = Number(dc['Call Later'] || 0);
  var callbackPie = Number(dc['Busy'] || 0) + Number(dc['Callback'] || 0);
  var answered = Number(dc['Answered'] || 0);
  var failed = Number(dc['Failed'] || 0);
  if (!failed && list.length) {
    failed = list.filter(isFailed).length;
  }

  var calledCount = Number(extras.calledCount);
  if (!Number.isFinite(calledCount) || calledCount < 0) {
    calledCount = list.filter(isCalled).length;
  }

  // Donut — full outbound cohort from API (not the chart row sample)
  var pieData = [interested, notInterested, callLaterPie, callbackPie, failed, answered];
  var pieSum = pieData.reduce(function (a, b) { return a + b; }, 0);
  if (chartPie) {
    chartPie.updateSeries(pieSum === 0 ? [0, 0, 0, 0, 0, 0] : pieData, true);
    chartPie.updateOptions({
      plotOptions: {
        pie: {
          donut: {
            labels: {
              show: true,
              total: {
                show: true,
                showAlways: true,
                formatter: function () { return String(pieSum); },
              },
            },
          },
        },
      },
    }, false, false);
  }

  // Timeline
  if (chartTimeline) {
    var datesIsoRaw = Array.isArray(st.timeline_dates_iso) ? st.timeline_dates_iso : [];
    var serTotals = coerceNumArray7(st.timeline_total_calls || []);
    var serInterested = coerceNumArray7(st.timeline_interested || []);
    var serInbound = coerceNumArray7(st.timeline_inbound_per_day || []);

    var datesIso = datesIsoRaw.length > 0 ? datesIsoRaw.slice() : new Array(7).fill('');
    var categories = datesIso.map(function (iso) { return formatTimelineAxisLabel(iso || ''); });
    var totalCallsData, interestedData, callbackData;

    var useServerTimeline = datesIsoRaw.length > 0 && serTotals.length === datesIsoRaw.length && serInterested.length === datesIsoRaw.length;
    if (useServerTimeline) {
      totalCallsData = serTotals.slice();
      interestedData = serInterested.slice();
      var inboundFromApi = Array.isArray(st.timeline_inbound_per_day) && st.timeline_inbound_per_day.length === datesIsoRaw.length;
      var cbFw = callbackCountsByDate || {};
      if (inboundFromApi) { callbackData = serInbound.slice(); }
      else {
        var wl3 = Array.isArray(st.timeline_week_labels) ? st.timeline_week_labels : [];
        callbackData = wl3.length === datesIsoRaw.length ? wl3.map(function (d) { return cbFw[d] || 0; }) : getLast7DaysUtc().map(function (d) { return cbFw[d] || 0; });
      }
    } else {
      var wl2 = Array.isArray(st.timeline_week_labels) ? st.timeline_week_labels : null;
      var last7Utc = getLast7DaysUtc();
      var cat2 = wl2 && wl2.length === 7 ? wl2.slice() : last7Utc;
      categories = cat2.slice();
      var idx = {};
      last7Utc.forEach(function (d) { idx[d] = true; });
      var totalCallsByDay = {}, interestedByDay = {};
      last7Utc.forEach(function (d) { totalCallsByDay[d] = 0; interestedByDay[d] = 0; });
      list.forEach(function (lead) {
        var ms = leadTimelineMs(lead);
        if (isNaN(ms)) return;
        var dayName = weekdayShortUtc(ms);
        if (!idx[dayName]) return;
        totalCallsByDay[dayName]++;
        if (effectiveDispo(lead) === 'Interested') interestedByDay[dayName]++;
      });
      totalCallsData = cat2.map(function (d) { return totalCallsByDay[d] || 0; });
      interestedData = cat2.map(function (d) { return interestedByDay[d] || 0; });
      var cb = callbackCountsByDate || {};
      callbackData = cat2.map(function (d) { return cb[d] || 0; });
    }

    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    var cTz = isDark ? { text: '#9C9CA0', border: '#1A1A1A' } : { text: '#6C6C70', border: '#E5E5E7' };
    chartTimeline.updateOptions({
      xaxis: { categories: categories, labels: { rotate: categories.length <= 14 ? -35 : -45, style: { colors: categories.map(function () { return cTz.text; }), fontSize: '10px' } } },
      yaxis: { min: 0, labels: { style: { colors: [cTz.text], fontSize: '9px' } } },
      grid: { borderColor: cTz.border, strokeDashArray: 4 },
    });
    chartTimeline.updateSeries([
      { name: 'Total Calls', data: totalCallsData },
      { name: 'Interested', data: interestedData },
      { name: 'Callbacks', data: callbackData },
    ], true);
  }

  // Conversion Gauge — interested / all called (server totals)
  var convRate = calledCount > 0 ? (interested / calledCount) * 100 : 0;
  if (chartConversion) {
    chartConversion.updateSeries([parseFloat(convRate.toFixed(1))], true);
  }

  // Campaign Progress (100% stacked bar)
  if (chartProgress) {
    var pc = extras.progressCounts || {};
    var connected = Number(pc.connected);
    var failedP = Number(pc.failed);
    var noAnswer = Number(pc.no_answer);
    var pending = Number(pc.pending);
    if (!Number.isFinite(connected)) {
      connected = list.filter(function (l) { return (l.status || '').toLowerCase() === 'completed'; }).length;
      failedP = list.filter(function (l) { var s = (l.status || '').toLowerCase(); return s === 'failed' || s === 'error'; }).length;
      noAnswer = list.filter(function (l) { var s = (l.status || '').toLowerCase(); return s === 'no answer' || s === 'busy'; }).length;
      pending = list.filter(function (l) { return (l.status || '').toLowerCase() === 'pending' || !l.status; }).length;
    }
    chartProgress.updateSeries([
      { name: 'Connected', data: [connected] },
      { name: 'Failed', data: [failedP] },
      { name: 'No Answer', data: [noAnswer] },
      { name: 'Pending', data: [pending] },
    ], true);
  }

  // Day of Week Distribution
  if (chartWeekday) {
    var weekday = Array.isArray(extras.weekdayCounts) && extras.weekdayCounts.length === 7
      ? extras.weekdayCounts.map(function (x) { return Number(x) || 0; })
      : null;
    if (!weekday) {
      weekday = [0, 0, 0, 0, 0, 0, 0];
      list.forEach(function (lead) {
        var ms = leadTimelineMs(lead);
        if (isNaN(ms)) return;
        var d = new Date(ms).getDay();
        var idx = d === 0 ? 6 : d - 1;
        if (idx >= 0 && idx <= 6) weekday[idx]++;
      });
    }
    chartWeekday.updateSeries([{ name: 'Calls', data: weekday }], true);
  }

  // Hourly Distribution
  if (typeof updateHourlyChartForLeads === 'function') {
      updateHourlyChartForLeads(list);
  }

  // Sparklines
  updateSparklines(list, st, extras);
}

function updateHourlyChartForLeads(filteredLeads) {
  if (!chartHourly) return;
  var hourly = Array(24).fill(0);

  if (filteredLeads && filteredLeads.length > 0) {
    var maxMs = -1;
    filteredLeads.forEach(function (lead) {
      var ms = leadTimelineMs(lead);
      if (!isNaN(ms) && ms > maxMs) maxMs = ms;
    });

    if (maxMs > 0) {
      var latestIstMs = maxMs + (5 * 60 + 30) * 60000;
      var latestDate = new Date(latestIstMs);
      var latestDayString = latestDate.getUTCFullYear() + '-' + latestDate.getUTCMonth() + '-' + latestDate.getUTCDate();

      filteredLeads.forEach(function (lead) {
        var ms = leadTimelineMs(lead);
        if (isNaN(ms)) return;
        var istMs = ms + (5 * 60 + 30) * 60000;
        var d = new Date(istMs);
        var dayString = d.getUTCFullYear() + '-' + d.getUTCMonth() + '-' + d.getUTCDate();
        if (dayString === latestDayString) {
          var h = d.getUTCHours();
          if (h >= 0 && h < 24) hourly[h]++;
        }
      });
    }
  }

  chartHourly.updateSeries([{ name: 'Calls', data: hourly }], true);
}

function updateSparklines(leads, st, extras) {
  extras = extras || {};
  var last7 = getLastSevenPlaceholderCategories();
  var days = st && Array.isArray(st.timeline_dates_iso) && st.timeline_dates_iso.length === 7
    ? st.timeline_dates_iso.slice()
    : last7;

  var cats = days.map(function (d) {
    if (d && /^\d{4}-\d{2}-\d{2}$/.test(d)) {
      return formatTimelineAxisLabel(d);
    }
    return d;
  });

  var useServer = st && Array.isArray(st.timeline_total_calls) && st.timeline_total_calls.length === 7;
  var totalByDay = useServer ? coerceNumArray7(st.timeline_total_calls) : Array(7).fill(0);
  var calledByDay = useServer ? totalByDay.slice() : Array(7).fill(0);
  var interestedByDay = useServer && Array.isArray(st.timeline_interested)
    ? coerceNumArray7(st.timeline_interested)
    : Array(7).fill(0);
  var notInterestedByDay = Array(7).fill(0);
  var failedByDay = Array(7).fill(0);
  var inboundByDay = Array(7).fill(0);

  if (!useServer) {
    var dayIndex = {};
    days.forEach(function (iso, i) {
      if (iso && /^\d{4}-\d{2}-\d{2}$/.test(iso)) dayIndex[iso] = i;
    });
    var list = Array.isArray(leads) ? leads : [];
    list.forEach(function (lead) {
      var ms = leadTimelineMs(lead);
      if (isNaN(ms)) return;
      var iso = new Date(ms).toISOString().slice(0, 10);
      var idx = dayIndex[iso];
      if (idx === undefined) return;
      totalByDay[idx]++;
      if (isCalled(lead)) {
        calledByDay[idx]++;
        var dispo = effectiveDispo(lead);
        if (dispo === 'Interested') interestedByDay[idx]++;
        else if (dispo === 'Not Interested' || dispo === 'not_interested') notInterestedByDay[idx]++;
        if (isFailed(lead)) failedByDay[idx]++;
      }
    });
  }

  if (st && Array.isArray(st.timeline_inbound_per_day) && st.timeline_inbound_per_day.length === 7) {
    inboundByDay = st.timeline_inbound_per_day.slice();
  }

  var RED = '#DC2626', GREEN = '#16A34A', GRAY = '#9CA3AF', PURPLE = '#9333EA', AMBER = '#D97706';

  var sparkConfigs = [
    { id: 'spark-total', data: totalByDay, color: GRAY },
    { id: 'spark-called', data: calledByDay, color: RED },
    { id: 'spark-interested', data: interestedByDay, color: GREEN },
    { id: 'spark-not-interested', data: notInterestedByDay, color: RED },
    { id: 'spark-inbound', data: inboundByDay, color: PURPLE },
    { id: 'spark-conversion', data: calledByDay.map(function (c, i) { return c > 0 ? Math.round((interestedByDay[i] / c) * 100) : 0; }), color: GREEN },
    { id: 'spark-attempts', data: totalByDay, color: RED },
    { id: 'spark-failed', data: failedByDay, color: RED },
  ];

  sparkConfigs.forEach(function (cfg) {
    var el = document.getElementById(cfg.id);
    if (!el) return;
    if (!sparkCharts[cfg.id]) {
      sparkCharts[cfg.id] = new ApexCharts(el, {
        series: [{ data: cfg.data }],
        chart: { type: 'area', height: 36, width: '100%', sparkline: { enabled: true }, background: 'transparent' },
        fill: { type: 'solid', opacity: 0.15 },
        stroke: { curve: 'smooth', width: 1.5 },
        colors: [cfg.color],
        tooltip: { enabled: false },
      });
      sparkCharts[cfg.id].render();
    } else {
      sparkCharts[cfg.id].updateSeries([{ data: cfg.data }], true);
    }
  });
}
