import request from 'supertest';
import server from '../server.js';

describe('GET /', () => {
  afterAll((done) => server.close(done));

  it('responds with 200 and greeting message', async () => {
    const res = await request(server).get('/');
    expect(res.status).toBe(200);
    expect(res.text).toContain('Hello from Fabric!');
  });
});
