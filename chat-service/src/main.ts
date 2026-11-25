import checkEnv, { ENV } from '@config/env';
import {
   connectKafkaProducer,
   disconnectKafkaProducer,
   startAllConsumer,
   stopAllConsumer,
} from '@config/kafka';
import { logger } from '@config/logger';
import { connectRedis, disconnectRedis } from '@infrastructure/cache/redis/client';
import connectDB from '@infrastructure/persistance/mongo/client';
import httpServer from '@presentation/websocket/ws';

const bootStrap = async () => {
   try {
      checkEnv();
      await connectDB();
      await connectRedis();
      process.on('SIGINT', shutdown);
      process.on('SIGTERM', shutdown);

      await connectKafkaProducer();

      httpServer.listen(Number(ENV.SERVER_PORT), () => {
         logger.info(`http+socket.io server running on port ${ENV.SERVER_PORT}`);
      });

      await startAllConsumer();
   } catch (error) {
      logger.error('error while starting chat-service-pod', { error });
   }
};

const shutdown = async () => {
   disconnectKafkaProducer();
   stopAllConsumer();
   disconnectRedis();
};

bootStrap();
