# 端到端验证清单

每个里程碑完成后，按本清单手工走查一遍。走查前启动服务：

```bash
conda activate docmind
uvicorn app.main:app --reload
```

## 第 1 周：入库 + 检索链路

- [ ] 上传 Markdown 文档：`curl -F "file=@scripts/sample_data/rag-简介.md" http://127.0.0.1:8000/api/documents/upload`，返回 `doc_id` 与 `chunk_count`
- [ ] 上传 Word 文档、PDF 文档、TXT 文档各一份（用自己的课程资料），全部成功
- [ ] 上传一份 GBK 编码的 txt，解析正常无乱码
- [ ] 上传不支持格式（如 .xyz）返回 400 与明确错误信息
- [ ] `GET /api/documents` 列表包含全部文档
- [ ] `POST /api/search`（body: `{"query": "什么是RAG", "strategy": "vector", "top_k": 5}`）返回相关片段
- [ ] 删除一个文档后：列表消失、检索不到该文档内容、`GET /api/health` 的 chunk_count 减少
- [ ] 重启服务后数据仍在（持久化验证）

## 第 2 周：MVP（聊天 + 前端）

- [ ] 浏览器打开 http://127.0.0.1:8000，界面正常
- [ ] 上传 2 个文档 → 提问 → 流式回答逐字渲染
- [ ] 回答附引用来源卡片，点击可定位原文
- [ ] 追问（如"那第二个呢"）能结合上下文回答（多轮对话）
- [ ] `stream: false` 请求返回完整 JSON（含 sources）
- [ ] 无文档时提问，返回友好提示而非报错

## 第 3 周：混合检索 + 评估

- [ ] `/api/search` 三种策略（vector / bm25 / hybrid）均可返回结果，bm25/hybrid 结果带 `rank_bm25`、`rank_vector` 字段
- [ ] 同一条查询三策略对比：`curl -X POST http://127.0.0.1:8000/api/search -H "Content-Type: application/json" -d '{"query":"什么是RAG","strategy":"hybrid","top_k":5}'`
- [ ] 开启重排有结果且带 `rerank_score` 字段（`"rerank": true`）
- [ ] 浏览器点击侧栏「检索台」：三策略并排显示、徽章展示两路排名、重排开关生效、Esc 关闭
- [ ] 测试集已生成（`eval/data/testset.jsonl`），按 `eval/data/testset.review.md` 抽查约 20% 并记录结论
- [ ] `python -X utf8 -m eval.evaluate` 一条命令输出全量对比表，`eval/results/grid_results.csv` 已生成

## 第 4 周：部署 + 压测

- [ ] locust 压测报告含 P50/P95/P99
- [ ] 公网 IP 访问完整流程，流式输出正常（nginx `proxy_buffering off` 生效）
- [ ] README 全部链接（demo、架构图、报告）可访问
