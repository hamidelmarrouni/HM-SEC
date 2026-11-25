import { startAllConsumers, stopAllConsumer } from '@config/kafka';
import { logger } from '@config/logger';
import checkEnv, { ENV } from '@config/env';
import connectDB from '@infrastructure/persistance/mongo/client';
import httpServer from '@presentation/websocket/ws';

const bootstrap = async () => {
   try {
      checkEnv();
      await connectDB();
      httpServer.listen(Number(ENV.SERVER_PORT), () => {
         logger.info(`http+socket.io server running on port ${ENV.SERVER_PORT}`);
      });

      process.on('SIGINT', shutdown);
      process.on('SIGTERM', shutdown);
      await startAllConsumers();

      logger.info('notification service fully operational');
   } catch (error) {
      logger.error('Error while starting notificaion serviec', { error });
   }
};

const shutdown = async () => {
   stopAllConsumer();
};

bootstrap();
