import express from 'express';
import cors from 'cors';
import morgan from 'morgan';
import fs from 'fs/promises';
import path from 'path';

const PORT = Number(process.env.PORT || 3010);
const MEDIA_DIR = process.env.HMSEC_MEDIA_DIR || path.resolve(process.cwd(), '../runtime/media');
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

const app = express();
app.use(cors({
   origin: [FRONTEND_URL, 'http://localhost:5173'],
   credentials: false,
   methods: ['GET', 'PUT', 'OPTIONS'],
   allowedHeaders: ['Content-Type'],
}));
app.use(morgan('dev'));

const safeKey = (raw: string) => {
   const decoded = decodeURIComponent(raw || '');
   const normalized = decoded.replace(/\\/g, '/').replace(/^\/+/, '');
   if (!normalized || normalized.includes('..')) throw new Error('Invalid media key');
   return normalized;
};

app.get('/api/v1/media/health', (_req, res) => res.json({ status: 'ok' }));

app.put(
   '/api/v1/media/upload',
   express.raw({ type: '*/*', limit: '100mb' }),
   async (req, res) => {
      try {
         const key = safeKey(String(req.query.key || ''));
         const target = path.join(MEDIA_DIR, key);
         await fs.mkdir(path.dirname(target), { recursive: true });
         await fs.writeFile(target, req.body as Buffer);
         res.status(200).json({ ok: true, key });
      } catch (error: any) {
         res.status(400).json({ ok: false, message: error?.message || 'upload failed' });
      }
   }
);

app.use('/media', express.static(MEDIA_DIR, { maxAge: 0 }));

fs.mkdir(MEDIA_DIR, { recursive: true }).then(() => {
   app.listen(PORT, () => console.log(`[HM_SEC media-service] listening on ${PORT}`));
});
