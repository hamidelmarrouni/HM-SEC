import { PrismaClient } from '../generated/prisma';

const db = new PrismaClient();
const userId = process.env.HMSEC_SEED_USER_ID;

async function main() {
   if (!userId) throw new Error('HMSEC_SEED_USER_ID is required');
   await db.humaneScore.upsert({
      where: { userId },
      update: {},
      create: { userId, score: 0 },
   });
   console.log(`HMSEC_REWARD_USER_ID=${userId}`);
}

main()
   .catch((error) => {
      console.error(error);
      process.exit(1);
   })
   .finally(async () => {
      await db.$disconnect();
   });
