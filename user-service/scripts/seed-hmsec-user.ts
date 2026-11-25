import { PrismaClient } from '../generated/prisma';
import bcrypt from 'bcryptjs';

const db = new PrismaClient();

type SeedUser = {
   firstName: string;
   lastName: string;
   email: string;
   password: string;
   admin?: boolean;
};

if (!process.env.HMSEC_SEED_PASSWORD) throw new Error('HMSEC_SEED_PASSWORD is required');

const users: SeedUser[] = [
   {
      firstName: process.env.HMSEC_SEED_FIRST_NAME || 'Demo',
      lastName: process.env.HMSEC_SEED_LAST_NAME || 'User',
      email: process.env.HMSEC_SEED_EMAIL || 'demo@example.test',
      password: process.env.HMSEC_SEED_PASSWORD!,
      admin: true,
   },
   { firstName: 'Brahim', lastName: 'Test', email: 'brahim@example.test', password: process.env.HMSEC_SEED_PASSWORD! },
   { firstName: 'Meryam', lastName: 'Test', email: 'meryam@example.test', password: process.env.HMSEC_SEED_PASSWORD! },
   { firstName: 'Ihssan', lastName: 'Test', email: 'ihssan@example.test', password: process.env.HMSEC_SEED_PASSWORD! },
];

async function upsertUser(input: SeedUser) {
   const passwordHash = await bcrypt.hash(input.password, 10);
   const user = await db.user.upsert({
      where: { email: input.email },
      update: {
         firstName: input.firstName,
         lastName: input.lastName,
         passwordHash,
         isEmailVerified: true,
         isBlocked: false,
      },
      create: {
         firstName: input.firstName,
         lastName: input.lastName,
         email: input.email,
         passwordHash,
         isEmailVerified: true,
         isBlocked: false,
      },
   });

   if (input.admin) {
      await db.admin.upsert({
         where: { email: input.email },
         update: { firstName: input.firstName, lastName: input.lastName, passwordHash },
         create: {
            firstName: input.firstName,
            lastName: input.lastName,
            email: input.email,
            passwordHash,
         },
      });
   }
   return user;
}

async function main() {
   const created = [];
   for (const input of users) {
      const user = await upsertUser(input);
      created.push(user);
      console.log(`HMSEC_ACCOUNT=${input.email}|${user.id}`);
   }

   const hamid = created[0];
   console.log(`HMSEC_USER_ID=${hamid.id}`);
   console.log(`HMSEC_USER_EMAIL=${hamid.email}`);
   console.log(`HMSEC_ADMIN_EMAIL=${users[0].email}`);
   console.log(`HMSEC_ALL_USER_IDS=${created.map((u) => u.id).join(',')}`);
}

main()
   .catch((error) => {
      console.error(error);
      process.exit(1);
   })
   .finally(async () => {
      await db.$disconnect();
   });
