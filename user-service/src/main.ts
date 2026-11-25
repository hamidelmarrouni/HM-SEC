import { logger } from '@config/logger';
import checkEnv, { ENV } from './config/env';
import app from './presentation/server';
import { connectKafkaProducer, disconnectKafkaProducer } from '@config/kafka';
import db from '@infrastructure/persistance/postgres/prisma-client';

const start = async () => {
   try {
      checkEnv();
      await db.$connect();

      await connectKafkaProducer();
      process.on('SIGINT', async () => {
         await disconnectKafkaProducer();
      });
      process.on('SIGTERM', async () => {
         await disconnectKafkaProducer();
      });

      app.listen(Number(ENV.SERVER_PORT), () => logger.info(`user service start listening on port ${ENV.SERVER_PORT}`));
   } catch (error) {
      logger.error('Error while starting user service', { error });
   }
};
start();
