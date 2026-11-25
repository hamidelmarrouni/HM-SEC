import express from 'express';
import cors from 'cors';
import morgan from 'morgan';
import mongoose from 'mongoose';
import axios from 'axios';

const PORT = Number(process.env.PORT || 3009);
const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/hm_sec_writer';
const USER_SERVICE_BASE_URL = process.env.USER_SERVICE_BASE_URL || 'http://127.0.0.1:3001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const MEDIA_BASE_URL =
   process.env.AWS_CLOUDFRONT_DISTRIBUTION_DOMAIN_NAME || 'http://127.0.0.1:9000/hm-sec-media';

const app = express();
app.use(cors({ origin: [FRONTEND_URL, 'http://localhost:5173'], credentials: true }));
app.use(express.json());
app.use(morgan('dev'));

const userApi = axios.create({ baseURL: `${USER_SERVICE_BASE_URL}/api/v1/internal/hmsec-query`, timeout: 5000 });

const arr = (v: unknown): string[] => {
   if (Array.isArray(v)) return v.map(String);
   if (v === undefined || v === null || v === '') return [];
   return [String(v)];
};
const toId = (x: any) => String(x?._id ?? x?.id ?? '');
const objectId = (id: string) => mongoose.Types.ObjectId.isValid(id) ? new mongoose.Types.ObjectId(id) : null;

async function userBasics(ids: string[]) {
   if (ids.length === 0) return [];
   const { data } = await userApi.get('/basic', {
      params: { userId: ids },
      paramsSerializer: { indexes: null } as any,
   });
   return data.data.user as any[];
}
async function userById(id: string) {
   try {
      const { data } = await userApi.get(`/${id}`);
      return data.data.user;
   } catch {
      return null;
   }
}
async function searchUsers(q: string, page: number, limit: number, currentUserId?: string) {
   const { data } = await userApi.get('/search', {
      params: { searchQuery: q, page, limit, currentUserId },
   });
   return data.data;
}
function mediaURL(doc: any) {
   const key = doc?.processedAttachmentKey || doc?.rawAttachmentKey;
   return key ? `${MEDIA_BASE_URL}/${key}` : null;
}
async function postsCollection() {
   if (!mongoose.connection.db) throw new Error('MongoDB not connected');
   return mongoose.connection.db.collection('posts');
}
async function commentsCollection() {
   if (!mongoose.connection.db) throw new Error('MongoDB not connected');
   return mongoose.connection.db.collection('comments');
}
async function hydratePost(doc: any, includeAuthor = true) {
   if (!doc) return null;
   const postId = toId(doc);
   const cc = await (await commentsCollection()).countDocuments({ postId: doc._id });
   let author: any = undefined;
   if (includeAuthor && doc.authorId) author = (await userBasics([String(doc.authorId)]))[0] ?? undefined;

   return {
      id: postId,
      authorId: String(doc.authorId),
      author,
      content: doc.content ?? '',
      visibility: doc.visibility ?? 'public',
      hashtags: doc.hashtags ?? [],
      attachmentType: doc.attachmentType ?? null,
      rawAttachmentKey: doc.rawAttachmentKey ?? null,
      attachmentStatus: doc.attachmentStatus ?? null,
      attachmentURL: mediaURL(doc),
      posterURL: mediaURL(doc),
      moderationStatus: doc.moderationStatus ?? 'pending',
      moderationMetadata: doc.moderationMetadata ?? null,
      createdAt: doc.createdAt,
      updatedAt: doc.updatedAt,
      commentCount: cc,
   };
}
async function hydrateComment(doc: any, includeAuthor = true) {
   if (!doc) return null;
   const author = includeAuthor && doc.authorId ? (await userBasics([String(doc.authorId)]))[0] ?? undefined : undefined;
   return {
      id: toId(doc),
      authorId: String(doc.authorId),
      postId: String(doc.postId),
      content: doc.content ?? '',
      createdAt: doc.createdAt,
      updatedAt: doc.updatedAt,
      likedByPostAuthor: doc.likedByPostAuthor ?? false,
      likeCount: doc.likeCount ?? 0,
      author,
   };
}

app.get('/metrics', (_req, res) => res.type('text/plain').send('hmsec_query_service_up 1\n'));
app.get('/api/v1/query/health', (_req, res) => res.json({ status: 'ok', backend: 'mongo+user-service' }));

app.get('/api/v1/query/public/user/basic', async (req, res, next) => {
   try {
      const ids = arr(req.query.userId);
      res.json({ success: true, message: 'ok', data: { user: await userBasics(ids) } });
   } catch (e) { next(e); }
});

app.get('/api/v1/query/internal/user', async (req, res, next) => {
   try {
      const q = String(req.query.searchQuery || '');
      const page = Math.max(1, Number(req.query.page || 1));
      const limit = Math.min(50, Math.max(1, Number(req.query.limit || 10)));
      const currentUserId = req.query.currentUserId ? String(req.query.currentUserId) : undefined;
      const data = await searchUsers(q, page, limit, currentUserId);
      res.json({ status: 200, message: 'ok', data });
   } catch (e) { next(e); }
});

app.get('/api/v1/query/public/user', async (req, res, next) => {
   try {
      const q = String(req.query.searchQuery || '');
      const limit = Math.min(50, Math.max(1, Number(req.query.limit || 15)));
      const offset = Math.max(0, Number(req.query.searchAfter || 0));
      const page = Math.floor(offset / limit) + 1;
      const data = await searchUsers(q, page, limit);
      const nextOffset = offset + data.users.length;
      res.json({
         success: true,
         message: 'ok',
         data: {
            users: data.users,
            scroll: {
               hasMore: Boolean(data.pagination?.hasMore),
               cursor: data.pagination?.hasMore ? nextOffset : null,
            },
         },
      });
   } catch (e) { next(e); }
});

app.get('/api/v1/query/public/user/:userId/humaneScore', async (req, res, next) => {
   try {
      const user = await userById(req.params.userId);
      res.json({ data: user ? { userId: user.id, score: user.humaneScore ?? 0 } : null });
   } catch (e) { next(e); }
});

app.get('/api/v1/query/public/user/:userId', async (req, res, next) => {
   try {
      const user = await userById(req.params.userId);
      if (!user) return res.status(404).json({ success: false, message: 'User not found', data: { user: null } });
      res.json({ success: true, message: 'ok', data: { user } });
   } catch (e) { next(e); }
});

app.get('/api/v1/query/internal/post', async (req, res, next) => {
   try {
      const ids = arr(req.query.postId);
      const oidPairs = ids.map((id) => [id, objectId(id)] as const).filter(([, oid]) => oid);
      const docs = await (await postsCollection()).find({ _id: { $in: oidPairs.map(([, oid]) => oid!) } }).toArray();
      const map = new Map(docs.map((d) => [toId(d), d]));
      const noAuthor = String(req.query.noAuthorHydration || '') === '1';
      const posts = await Promise.all(ids.map((id) => hydratePost(map.get(id), !noAuthor)));
      res.json({ message: 'ok', data: { posts } });
   } catch (e) { next(e); }
});

app.get('/api/v1/query/internal/comment', async (req, res, next) => {
   try {
      const ids = arr(req.query.commentId);
      const oids = ids.map(objectId).filter(Boolean) as mongoose.Types.ObjectId[];
      const docs = await (await commentsCollection()).find({ _id: { $in: oids } }).toArray();
      const map = new Map(docs.map((d) => [toId(d), d]));
      const comments = await Promise.all(ids.map((id) => hydrateComment(map.get(id), false)));
      res.json({ data: { comments } });
   } catch (e) { next(e); }
});

app.get('/api/v1/query/post/timeline/:userId', async (req, res, next) => {
   try {
      const limit = Math.min(50, Math.max(1, Number(req.query.limit || 5)));
      const from = req.query.from ? String(req.query.from) : null;
      const filter: any = { authorId: req.params.userId };
      const fromOid = from ? objectId(from) : null;
      if (fromOid) filter._id = { $lt: fromOid };
      const docs = await (await postsCollection()).find(filter).sort({ _id: -1 }).limit(limit + 1).toArray();
      const hasMore = docs.length > limit;
      const pageDocs = docs.slice(0, limit);
      const posts = await Promise.all(pageDocs.map((d) => hydratePost(d, true)));
      const targetUserDetails = (await userBasics([req.params.userId]))[0] ?? null;
      res.json({
         message: 'ok',
         data: {
            posts,
            pagination: { from: hasMore && pageDocs.length ? toId(pageDocs[pageDocs.length - 1]) : null, hasMore },
            targetUserDetails,
         },
      });
   } catch (e) { next(e); }
});

app.get('/api/v1/query/post/hashtag/:hashtag', async (req, res, next) => {
   try {
      const limit = Math.min(50, Math.max(1, Number(req.query.limit || 5)));
      const from = req.query.from ? String(req.query.from) : null;
      const tag = req.params.hashtag.replace(/^#/, '');
      const filter: any = { hashtags: { $in: [tag, `#${tag}`] } };
      const fromOid = from ? objectId(from) : null;
      if (fromOid) filter._id = { $lt: fromOid };
      const docs = await (await postsCollection()).find(filter).sort({ _id: -1 }).limit(limit + 1).toArray();
      const hasMore = docs.length > limit;
      const pageDocs = docs.slice(0, limit);
      const posts = await Promise.all(pageDocs.map((d) => hydratePost(d, true)));
      res.json({
         message: 'ok',
         data: {
            posts,
            pagination: { from: hasMore && pageDocs.length ? toId(pageDocs[pageDocs.length - 1]) : null, hasMore },
         },
      });
   } catch (e) { next(e); }
});

app.get('/api/v1/query/post/:postId/comment', async (req, res, next) => {
   try {
      const postId = objectId(req.params.postId);
      if (!postId) return res.json({ message: 'ok', data: { comments: [], pagination: { from: null, hasMore: false } } });
      const limit = Math.min(50, Math.max(1, Number(req.query.limit || 10)));
      const from = req.query.from ? String(req.query.from) : null;
      const filter: any = { postId };
      const fromOid = from ? objectId(from) : null;
      if (fromOid) filter._id = { $lt: fromOid };
      const docs = await (await commentsCollection()).find(filter).sort({ _id: -1 }).limit(limit + 1).toArray();
      const hasMore = docs.length > limit;
      const pageDocs = docs.slice(0, limit);
      const comments = await Promise.all(pageDocs.map((d) => hydrateComment(d, true)));
      res.json({
         message: 'ok',
         data: {
            comments,
            pagination: { from: hasMore && pageDocs.length ? toId(pageDocs[pageDocs.length - 1]) : null, hasMore },
         },
      });
   } catch (e) { next(e); }
});

app.get('/api/v1/query/post/:postId', async (req, res, next) => {
   try {
      const oid = objectId(req.params.postId);
      if (!oid) return res.status(404).json({ message: 'Post not found', data: { post: null } });
      const doc = await (await postsCollection()).findOne({ _id: oid });
      if (!doc) return res.status(404).json({ message: 'Post not found', data: { post: null } });
      res.json({ message: 'ok', data: { post: await hydratePost(doc, true) } });
   } catch (e) { next(e); }
});

app.use((err: any, _req: any, res: any, _next: any) => {
   console.error('[HM_SEC query-service]', err?.message || err);
   res.status(500).json({ success: false, message: 'HM_SEC query service error' });
});

async function start() {
   await mongoose.connect(MONGODB_URI);
   app.listen(PORT, () => console.log(`[HM_SEC query-service] listening on ${PORT}`));
}
start().catch((e) => {
   console.error('[HM_SEC query-service] startup failed', e);
   process.exit(1);
});
