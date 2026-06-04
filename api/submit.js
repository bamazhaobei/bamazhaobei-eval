// POST /api/submit — receives evaluation data and stores in Vercel Blob
import { put, head, list } from '@vercel/blob';

export default async function handler(req, res) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const body = req.body;
    
    // Validate required fields
    if (!body.score) {
      return res.status(400).json({ error: 'Missing required field: score' });
    }

    // Add timestamp and metadata
    const record = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      timestamp: new Date().toISOString(),
      userAgent: req.headers['user-agent'] || '',
      ip: req.headers['x-forwarded-for'] || req.socket.remoteAddress || '',
      score: body.score,
      province: body.province || '',
      industry: body.industry || '',
      incomeLevel: body.incomeLevel || '',
      practice: body.practice || '',
      exam: body.exam || '',
      topSchools: body.topSchools || [],
      topScores: body.topScores || [],
      feedback: body.feedback || ''
    };

    // Read existing data from Blob
    let allData = [];
    try {
      const { blobs } = await list({ prefix: 'evaluations' });
      if (blobs.length > 0) {
        const response = await fetch(blobs[0].url);
        allData = await response.json();
      }
    } catch (e) {
      // First record, no existing data
    }

    // Append new record
    allData.push(record);

    // Write back to Blob
    const blobKey = `evaluations/eval-${new Date().toISOString().slice(0, 7)}.json`;
    await put(blobKey, JSON.stringify(allData), {
      access: 'public',
      addRandomSuffix: false,
      contentType: 'application/json'
    });

    return res.status(200).json({ ok: true, id: record.id });
  } catch (error) {
    console.error('Submit error:', error);
    return res.status(500).json({ error: 'Internal server error' });
  }
}
