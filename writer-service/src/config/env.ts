export const ENV = {
   NODE_ENV: (process.env.NODE_ENV || 'development') as 'production' | 'development',
   SERVER_PORT: process.env.PORT || '3002',
   ACCESS_TOKEN_SECRET: process.env.accessTokenSecret,
   KAFKA_CLIENT_ID: process.env.KAFKA_CLIENT_ID || 'hmsec-writer-service',
   KAFKA_BROKER_URI: process.env.KAFKA_BROKER_URI || '127.0.0.1:9092',
   MONGODB_URI: process.env.MONGODB_URI,
   AWS_ACCESS_KEY: process.env.AWS_ACCESS_KEY || 'hmsec',
   AWS_SECRET_KEY: process.env.AWS_SECRET_KEY || 'hmsec-local-secret',
   AWS_REGION: process.env.AWS_REGION || 'us-east-1',
   AWS_S3_BUCKET_NAME: process.env.AWS_S3_BUCKET_NAME || 'hm-sec-media',
   AWS_CLOUDFRONT_DISTRIBUTION_DOMAIN_NAME:
      process.env.AWS_CLOUDFRONT_DISTRIBUTION_DOMAIN_NAME || 'http://127.0.0.1:9000/hm-sec-media',
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
