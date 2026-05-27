---
name: document-rag
display_name: 文档检索与解读
description: 对制度/报告做元数据预过滤+混合检索+rerank 的 RAG；制度仅现行版本；强制给出处；查不到说查不到。
type: general
when_to_use: 制度问答或需要报告类定性证据时。
tools: [search_documents]
uses_skills: []
guardrails: [查不到不臆造, 必须给出处, 制度只引现行版本, 结构化数据禁用本 skill]
---

# 文档检索与解读 (G3)

制度/流程类问题走 RAG，封装在 search_documents 内。

## SOP

1. 由 entities 得 meta_filters（事业部/周期/类型，制度加 only_current）
2. 调 search_documents（内部向量+BM25+RRF+rerank）
3. 取 top-k 片段作为 evidence，附 doc_id/seq/title_path
4. 无命中时不臆造，提示换说法或声明未找到

硬约束：命中为 0 段时，必须直接回"未找到相关制度/报告"，禁止用 LLM 自由发挥或润色编出看似合理的规定/办法/流程；不得把"建议走某系统导出"等编造内容当答案。

## Few-shot

输入: "年假怎么规定"
→ search_documents("年假规定", {类型:制度, only_current:true})
→ [{doc_id:12, name:"员工手册(2025现行版)", seq:"4.2节", text:"入职满1年5天…", score:0.93}]
