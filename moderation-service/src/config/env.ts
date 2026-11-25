export const ENV = {
   NODE_ENV: (process.env.NODE_ENV || 'development') as 'production' | 'development',
   SERVER_PORT: process.env.PORT || '3007',
   KAFKA_BROKER_URI: process.env.KAFKA_BROKER_URI || '127.0.0.1:9092',
   KAFKA_CLIENT_ID: process.env.KAFKA_CLIENT_ID || 'hmsec-moderation-service',
   HMSEC_DEV_AUTO_APPROVE: process.env.HMSEC_DEV_AUTO_APPROVE !== 'false',
} as const;

function checkEnv() {
   return;
}
export default checkEnv;
