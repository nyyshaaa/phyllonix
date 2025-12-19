
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    cached_products: {
      executor: 'constant-vus',
      vus: 50,
      duration: '10s',
      exec: 'cachedProducts',
    },
    non_cached_products: {
      executor: 'constant-vus',
      vus: 50,
      duration: '10s',
      exec: 'nonCachedProducts',
    },
  },

  thresholds: {
    'http_req_duration{scenario:cached_products}': ['p(95)<200'],
    'http_req_duration{scenario:non_cached_products}': ['p(95)<600'],
  },
};

const BASE_URL =
  __ENV.BASE_URL ??
  'http://127.0.0.1:8000/api/v1';

export function cachedProducts() {
  const res = http.get(`${BASE_URL}/products?limit=20`);
  check(res, { 'cached 200': r => r.status === 200 });
}

export function nonCachedProducts() {
  const res = http.get(`${BASE_URL}/products/without_cache/?limit=20`);
  check(res, { 'non-cached 200': r => r.status === 200 });
}
