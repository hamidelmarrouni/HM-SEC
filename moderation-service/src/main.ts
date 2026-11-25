import express from 'express';
import { Kafka } from 'kafkajs';
import {
   AppEvent,
   AppEventsTypes,
   createEvent,
   MessageBrokerTopics,
} from 'humane-common';
import { ENV } from '@config/env';

const app = express();
app.use(express.json());

app.get('/metrics', (_req, res) => {
   res.type('text/plain').send('hmsec_moderation_up 1\n');
});
app.get('/api/v1/moderation/health', (_req, res) => {
   res.status(200).json({ status: 'ok', mode: 'hmsec-local-auto-approve' });
});

const kafka = new Kafka({
   clientId: ENV.KAFKA_CLIENT_ID,
   brokers: [ENV.KAFKA_BROKER_URI],
});
const producer = kafka.producer();
const consumer = kafka.consumer({ groupId: 'hmsec-moderation-auto-approve-v1' });

async function start() {
   await producer.connect();
   await consumer.connect();
   await consumer.subscribe({ topic: MessageBrokerTopics.POST_CREATE_EVENTS_TOPIC, fromBeginning: true });

   await consumer.run({
      eachMessage: async ({ message }) => {
         if (!message.value) return;
         const event = JSON.parse(message.value.toString()) as AppEvent;
         if (event.eventType !== AppEventsTypes.POST_CREATED) return;

         const payload = event.payload as any;
         if (!payload?.id) return;

         const approved = createEvent(AppEventsTypes.POST_MODERATED, {
            postId: payload.id,
            result: {
               success: true,
               flagged: false,
            },
         });

         await producer.send({
            topic: MessageBrokerTopics.CONTENT_MODERATION_EVENT_TOPIC,
            messages: [{ value: JSON.stringify(approved) }],
         });

         console.log(`[HM_SEC moderation] auto-approved post ${payload.id}`);
      },
   });

   const server = app.listen(Number(ENV.SERVER_PORT), () => {
      console.log(`[HM_SEC moderation] listening on ${ENV.SERVER_PORT}`);
   });

   const shutdown = async () => {
      server.close();
      await consumer.disconnect().catch(() => {});
      await producer.disconnect().catch(() => {});
      process.exit(0);
   };
   process.on('SIGINT', shutdown);
   process.on('SIGTERM', shutdown);
}

start().catch((error) => {
   console.error('[HM_SEC moderation] startup failed', error);
   process.exit(1);
});
