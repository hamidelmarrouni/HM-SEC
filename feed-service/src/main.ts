import checkEnv, { ENV } from '@config/env';
import { startAllConsumers, stopAllConsumer } from '@config/kafka';
import { logger } from '@config/logger';
import { connectRedis, disconnectRedis } from '@infrastructure/cache/redis/client';
import connectDB from '@infrastructure/persistance/mongoDB/mongoDBclient';
import app from '@presentation/http/app';

const bootstrap = async () => {
   try {
      checkEnv();
      await connectDB();
      await connectRedis();

      const server = app.listen(Number(ENV.SERVER_PORT), () => {
         logger.info(`feed server started listening on port ${ENV.SERVER_PORT}`);
      });

      try {
         await startAllConsumers();
         logger.info('Feed Kafka consumers started successfully');
      } catch (error) {
         logger.error('Feed HTTP is online, but Kafka consumers failed to start', { error });
      }

      const shutdown = async () => {
         server.close();
         disconnectRedis();
         await stopAllConsumer().catch(() => {});
      };
      process.on('SIGINT', shutdown);
      process.on('SIGTERM', shutdown);

      logger.info('Feed service started successfully');
   } catch (error) {
      logger.error('Error starting feed service', { error });
   }
};

bootstrap();
