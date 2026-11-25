export const ENV = {
   NODE_ENV: (process.env.NODE_ENV || 'development') as 'production' | 'development',
   SERVER_PORT: process.env.PORT || '3005',
   ACCESS_TOKEN_SECRET: process.env.accessTokenSecret,
   KAFKA_CLIENT_ID: process.env.KAFKA_CLIENT_ID || 'hmsec-notification-service',
   KAFKA_BROKER_URI: process.env.KAFKA_BROKER_URI || '127.0.0.1:9092',
   MONGODB_URI: process.env.MONGODB_URI,
   ELASTICSEARCH_PROXY_BASE_URL:
      process.env.ELASTICSEARCH_PROXY_BASE_URL || 'http://127.0.0.1:3009',
} as const;

function checkEnv() {
   const required = ['ACCESS_TOKEN_SECRET', 'MONGODB_URI'] as const;
   const missing = required.filter((key) => !ENV[key]);
   if (missing.length > 0) {
      missing.forEach((key) => console.error(`${key} not found in environment`));
      throw new Error('Required environment variables missing');
   }
}
export default checkEnv;
