
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 50,
  duration: '10s',
  thresholds: {
    http_req_duration: ['p(95)<200'],
  },
};

const BASE_URL =
  __ENV.BASE_URL ??
  'http://127.0.0.1:8000/api/v1';

export default function cachedProducts() {
  const res = http.get(`${BASE_URL}/products?limit=10`);
  check(res, { 'cached 200': r => r.status === 200 });
}

// export default function nonCachedProducts() {
//   const res = http.get(`${BASE_URL}/products/without_cache/?limit=20`);
//   check(res, { 'non-cached 200': r => r.status === 200 });
// }
