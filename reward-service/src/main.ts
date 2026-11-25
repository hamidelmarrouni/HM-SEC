import checkEnv, { ENV } from '@config/env';
import {
   connectKafkaProducer,
   disconnectKafkaProducer,
   startAllConsumer,
   stopAllConsumer,
} from '@config/kafka';
import { rewardConfigServices } from '@di/usecase/reward.usecase.constiner';
import db from '@infrastructure/persistance/postgres/prisma-client';
import app from '@presentation/http/server';
import { logger } from '@config/logger';

const bootStrap = async () => {
   try {
      checkEnv();
      await db.$connect();
      await rewardConfigServices.initializeRewardAmount();

      const server = app.listen(Number(ENV.SERVER_PORT), () => {
         logger.info(`Reward service started listening on port ${ENV.SERVER_PORT}`);
      });

      try {
         await connectKafkaProducer();
         await startAllConsumer();
         logger.info('Reward Kafka consumers started successfully');
      } catch (error) {
         logger.error('Reward HTTP is online, but Kafka consumers failed to start', { error });
      }

      const cleanup = async () => {
         server.close();
         await disconnectKafkaProducer().catch(() => {});
         await stopAllConsumer().catch(() => {});
      };
      process.on('SIGINT', cleanup);
      process.on('SIGTERM', cleanup);
   } catch (error) {
      logger.error('error while starting reward service', { error });
   }
};

bootStrap();
