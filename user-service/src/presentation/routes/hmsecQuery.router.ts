import express from 'express';
import db from '@infrastructure/persistance/postgres/prisma-client';
import { ENV } from '@config/env';

const router = express.Router();

const cdn = (key?: string | null) =>
   key ? `${ENV.AWS_CLOUDFRONT_DISTRIBUTION_DOMAIN_NAME}/${key}` : null;

const toBasic = (u: any) => ({
   id: u.id,
   firstName: u.firstName,
   lastName: u.lastName ?? null,
   avatarURL: cdn(u.avatarKey),
});

const toPublic = (u: any) => ({
   id: u.id,
   firstName: u.firstName,
   lastName: u.lastName ?? null,
   bio: u.bio ?? '',
   createdAt: u.createdAt,
   updatedAt: u.updatedAt,
   lastLoginTime: u.lastLoginTime,
   isBlocked: u.isBlocked,
   isHotUser: u.isHotUser,
   avatarKey: u.avatarKey ?? null,
   coverPhotoKey: u.coverPhotoKey ?? null,
   avatarURL: cdn(u.avatarKey),
   coverPhotoURL: cdn(u.coverPhotoKey),
   humaneScore: u.humaneScore ?? 0,
});

router.get('/basic', async (req, res) => {
   const raw = req.query.userId;
   const ids = Array.isArray(raw) ? raw.map(String) : raw ? [String(raw)] : [];
   if (ids.length === 0) return res.json({ data: { user: [] } });

   const users = await db.user.findMany({ where: { id: { in: ids } } });
   const map = new Map(users.map((u) => [u.id, u]));
   return res.json({ data: { user: ids.map((id) => (map.get(id) ? toBasic(map.get(id)) : null)) } });
});

router.get('/search', async (req, res) => {
   const searchQuery = String(req.query.searchQuery || '').trim();
   const currentUserId = req.query.currentUserId ? String(req.query.currentUserId) : undefined;
   const page = Math.max(1, Number(req.query.page || 1));
   const limit = Math.min(50, Math.max(1, Number(req.query.limit || 10)));
   const skip = (page - 1) * limit;

   const where: any = { isBlocked: false };
   if (currentUserId) where.id = { not: currentUserId };
   if (searchQuery) {
      where.OR = [
         { firstName: { contains: searchQuery, mode: 'insensitive' } },
         { lastName: { contains: searchQuery, mode: 'insensitive' } },
         { email: { contains: searchQuery, mode: 'insensitive' } },
      ];
   }

   const [total, users] = await Promise.all([
      db.user.count({ where }),
      db.user.findMany({
         where,
         orderBy: [{ firstName: 'asc' }, { id: 'asc' }],
         skip,
         take: limit,
      }),
   ]);

   return res.json({
      data: {
         users: users.map((u) => ({
            id: u.id,
            firstName: u.firstName,
            lastName: u.lastName ?? null,
            avatarURL: cdn(u.avatarKey),
         })),
         pagination: {
            page,
            limit,
            total,
            hasMore: skip + users.length < total,
         },
      },
   });
});

router.get('/:userId', async (req, res) => {
   const user = await db.user.findUnique({ where: { id: req.params.userId } });
   if (!user) return res.status(404).json({ message: 'User not found', data: { user: null } });
   return res.json({ data: { user: toPublic(user) } });
});

export default router;
