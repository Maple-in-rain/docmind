const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = { URL };
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/paths.js'), 'utf8'), context);

test('root deployment keeps API requests at root', () => {
  assert.equal(context.apiUrl('/api/chat', 'http://127.0.0.1:8000/'), 'http://127.0.0.1:8000/api/chat');
});

test('HTTPS prefix keeps all endpoints inside DocMind', () => {
  for (const endpoint of ['/api/chat', '/api/agent', '/api/documents', '/api/documents/3', '/api/documents/upload', '/api/search']) {
    assert.equal(context.apiUrl(endpoint, 'https://42.192.115.149/docmind/'), 'https://42.192.115.149/docmind' + endpoint);
  }
});
