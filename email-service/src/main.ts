import checkEnv, { ENV } from '@config/env';
import { connectKafkaProducer, startAllConsumers } from '@config/kafka';
import { logger } from '@config/logger';
import { shutdownCleanup } from '@config/shutdown';
import app from '@presentation/http/server';

const bootstrap = async () => {
   try {
      checkEnv();
      const server = app.listen(Number(ENV.SERVER_PORT), () => {
         logger.info(`Email service start listening on ${ENV.SERVER_PORT}`);
      });

      try {
         await connectKafkaProducer();
         await startAllConsumers();
         logger.info('Email Kafka consumers started successfully');
      } catch (error) {
         logger.error('Email HTTP is online, but Kafka startup failed', { error });
      }

      process.on('SIGINT', shutdownCleanup);
      process.on('SIGTERM', shutdownCleanup);
      return server;
   } catch (error) {
      logger.error('error while starting email service', { error });
   }
};

bootstrap();
