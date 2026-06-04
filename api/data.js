// GET /api/data?pwd=xxx — returns evaluation data (password protected)
import { list, put } from '@vercel/blob';

const ADMIN_PWD = 'bamazhaobei2026'; // Change this to your password

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const { pwd, format, start, end } = req.query;

  // If no password or wrong password, show summary only
  if (!pwd || pwd !== ADMIN_PWD) {
    // Return summary stats without detailed data
    return res.status(200).json({
      type: 'summary',
      message: '需要密码查看详细数据',
      totalRecords: '?',
      lastUpdated: '?'
    });
  }

  // Authenticated — return data
  try {
    let allData = [];
    const { blobs } = await list({ prefix: 'evaluations' });
    
    // Collect all evaluation files
    for (const blob of blobs) {
      try {
        const response = await fetch(blob.url);
        const data = await response.json();
        allData = allData.concat(data);
      } catch {}
    }

    // Sort by timestamp descending
    allData.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    // Date filter
    let filtered = allData;
    if (start) filtered = filtered.filter(r => r.timestamp >= start);
    if (end) filtered = filtered.filter(r => r.timestamp <= end);

    // Calculate stats
    const total = filtered.length;
    const scoreDistribution = {};
    const provinceStats = {};
    const industryStats = {};

    for (const r of filtered) {
      const bucket = Math.floor(r.score / 50) * 50;
      scoreDistribution[`${bucket}-${bucket + 50}`] = (scoreDistribution[`${bucket}-${bucket + 50}`] || 0) + 1;
      
      if (r.province) provinceStats[r.province] = (provinceStats[r.province] || 0) + 1;
      if (r.industry) industryStats[r.industry] = (industryStats[r.industry] || 0) + 1;
    }

    // Format for export
    if (format === 'csv') {
      res.setHeader('Content-Type', 'text/csv; charset=utf-8');
      res.setHeader('Content-Disposition', 'attachment; filename=evaluation-data.csv');
      const header = '时间,分数,省份,行业方向,收入目标,实操意愿,考研意愿,Top1学校,Top1分数,Top2学校,Top2分数,Top3学校,Top3分数';
      const rows = filtered.map(r => {
        const ts = r.timestamp ? new Date(r.timestamp).toLocaleString('zh-CN') : '';
        const t1 = r.topSchools?.[0] || ''; const s1 = r.topScores?.[0] || '';
        const t2 = r.topSchools?.[1] || ''; const s2 = r.topScores?.[1] || '';
        const t3 = r.topSchools?.[2] || ''; const s3 = r.topScores?.[2] || '';
        return `"${ts}","${r.score}","${r.province}","${r.industry}","${r.incomeLevel}","${r.practice}","${r.exam}","${t1}","${s1}","${t2}","${s2}","${t3}","${s3}"`;
      }).join('\n');
      return res.status(200).send('\uFEFF' + header + '\n' + rows);
    }

    // Return JSON
    return res.status(200).json({
      type: 'full',
      total,
      scoreDistribution,
      provinceStats,
      industryStats,
      records: filtered.slice(0, 500) // limit to 500 per request
    });
  } catch (error) {
    console.error('Data error:', error);
    return res.status(500).json({ error: 'Internal server error' });
  }
}
