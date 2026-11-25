import { logger } from '@config/logger';
import { createClient } from 'redis';

export const redisClient = createClient({ url: process.env.REDIS_URL || 'redis://127.0.0.1:6379' }).on('error', (err) =>
   console.log('Redis Client Error', err)
);
export const connectRedis = async () => {
   await redisClient.connect();
   logger.info('redis client connected');
};

export const disconnectRedis = () => {
   redisClient.destroy();
   logger.info('redis client disconnected');
};
