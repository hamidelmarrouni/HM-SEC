import { ENV } from '@config/env';
import {
   connectKafkaProducer,
   disconnectKafkaProducer,
   startAllConsumer,
   stopAllConsumer,
} from '@config/kafka';
import { logger } from '@config/logget';
import connectDB from '@infrastructure/persistance/MongoDB/mongoDBclient';
import app from '@presentation/http/app';

const bootstrap = async () => {
   try {
      await connectDB();

      await connectKafkaProducer();
      process.on('SIGINT', cleanup);
      process.on('SIGTERM', cleanup);

      app.listen(Number(ENV.SERVER_PORT), () => {
         logger.info(`writer server started on port ${ENV.SERVER_PORT}`);
      });

      await startAllConsumer();
      logger.info('writer server full operational');
   } catch (error) {
      logger.error('Error starting writer service', { error });
   }
};

const cleanup = () => {
   stopAllConsumer();
   disconnectKafkaProducer();
};

bootstrap();
