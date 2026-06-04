# 复盘报告页面改进 TODO

**日期**: 2026-05-28  
**参考规格**: 复盘Agent实现规格.md §6 前端展示 + 前端页面规格-权限重构.md §3.5

---

## 📋 改进清单

### ✅ 已完成
1. ✅ 复盘报告周期选择器（支持增量报告）
2. ✅ Mock数据接口集成
3. ✅ 基础权限控制（can ViewReview/canTrackTickets）

### ⏸ 待实现（按优先级）

#### P0 - 核心功能

**1. 三按钮操作**  
- [ ] 为每条建议添加三个按钮：「采纳→生成工单」「驳回」「存疑」
- [ ] 点「驳回」弹小窗填理由（归因不准/无可改进/重复建议/其他）
- [ ] 驳回后status=rejected并留档

**2. 事实vs推测标签**  
- [ ] 每条finding明显区分「事实」和「推测」  
- [ ] [事实] 用绿色/灰色标签  
- [ ] [推测] 用橙色/浅色标签，必须标「待人确认」

**3. 依据可展开**  
- [ ] 「依据:N个run」可点击展开  
- [ ] 展开后显示run_id列表（元信息：run_id, intent, outcome, badcase_reason, 时间）  
- [ ] 绝不展示query原文

#### P1 - 交互优化

**4. 采纳工单确认弹层**  
- [ ] 点「采纳→生成工单」弹确认弹层  
- [ ] 弹层内容：建议正文、依据run_id（可展开）、工单草稿、负责人=技术主管（固定）
- [ ] 底部 [取消] [生成工单] 按钮  
- [ ] 生成后status=accepted，按钮变成"已生成工单 #012 →"链接

**5. Status角标**  
- [ ] pending（默认，灰色）
- [ ] accepted（绿色，带工单号链接）  
- [ ] rejected（灰色）  
- [ ] hold（黄色，存疑状态）

#### P2 - 管理功能

**6. 立即重新生成按钮**  
- [ ] 页面右上角添加「立即重新生成本周报告」按钮  
- [ ] 仅tech_super_admin可见  
- [ ] biz_super_admin看到的是只读模式，按钮隐藏

---

## 🎨 UI/UX 设计规范

### 标签样式

```html
<!-- 事实标签 -->
<span class="finding-badge fact">[事实]</span>

<!-- 推测标签 -->
<span class="finding-badge hypothesis">[推测·待人确认]</span>
```

```css
.finding-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  margin-right: 6px;
}

.finding-badge.fact {
  background: #E8F5E9;
  color: #2E7D32;
  border: 1px solid #A5D6A7;
}

.finding-badge.hypothesis {
  background: #FFF3E0;
  color: #E65100;
  border: 1px solid #FFCC80;
}
```

### Status角标

```html
<!-- pending -->
<span class="suggestion-status pending">待处理</span>

<!-- accepted -->
<span class="suggestion-status accepted">
  已采纳 
  <a href="#" onclick="showTicket(12)">工单#012→</a>
</span>

<!-- rejected -->
<span class="suggestion-status rejected">已驳回</span>

<!-- hold -->
<span class="suggestion-status hold">存疑</span>
```

```css
.suggestion-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.suggestion-status.pending {
  background: #F5F5F5;
  color: #666;
}

.suggestion-status.accepted {
  background: #E8F5E9;
  color: #2E7D32;
}

.suggestion-status.accepted a {
  color: #2E7D32;
  text-decoration: underline;
}

.suggestion-status.rejected {
  background: #EEEEEE;
  color: #999;
}

.suggestion-status.hold {
  background: #FFF9C4;
  color: #F57F17;
}
```

---

## 💻 代码实现指南

### 1. 修改 `loadReviewPageWithFilter()` 函数

文件: `frontend/permission-admin.js`

```javascript
async function loadReviewPageWithFilter(){
  const host = $('adminReviewBody'); if(!host) return;
  const selector = $('reviewWeekSelector');
  const selectedWeek = selector ? selector.value : 'latest';
  
  try{
    const data = await global.apiGet('/admin/review/report', {week: selectedWeek});
    $('reviewPeriod').textContent = data.period || '';
    
    // 量化概览
    const m = data.metrics || {};
    let html = `<div class="admin-card"><h3 style="margin:0 0 12px;font-size:15px">量化概览（全量聚合）</h3>`;
    html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:8px">`;
    html += `<div><b>总问答</b><br>${m.total_qa||0}</div>`;
    html += `<div><b>👎率</b><br>${((m.down_rate||0)*100).toFixed(1)}%</div>`;
    html += `<div><b>超时率</b><br>${((m.timeout_rate||0)*100).toFixed(1)}%</div>`;
    html += `<div><b>RAG0命中</b><br>${((m.rag_zero_rate||0)*100).toFixed(1)}%</div>`;
    html += `</div></div>`;
    
    // 问题归类（区分事实/推测）
    if(data.findings && data.findings.length){
      html += `<div class="admin-card"><h3 style="margin:0 0 12px;font-size:15px">问题归类与归因</h3>`;
      html += (data.findings||[]).map(f=>{
        const isFact = f.type === 'fact';  // 后端应返回type字段
        const badge = isFact 
          ? `<span class="finding-badge fact">[事实]</span>` 
          : `<span class="finding-badge hypothesis">[推测·待人确认]</span>`;
        const runIds = f.run_ids || [];  // 后端应返回run_ids数组
        const evidence = `<a href="#" onclick="expandEvidence('${f.id}', event)" class="evidence-link">依据:${f.run_count||0}个run</a>`;
        const evidenceDetail = `<div id="evidence-${f.id}" class="evidence-detail" style="display:none"></div>`;
        
        return `
          <div style="margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid #eee">
            <div>${badge}<b>${global.escAi(f.text||'')}</b></div>
            <div class="muted" style="margin-top:4px">${global.escAi(f.hypothesis||'')} · ${evidence}</div>
            ${evidenceDetail}
          </div>
        `;
      }).join('');
      html += `</div>`;
    }
    
    // 改进建议（三按钮 + status角标）
    html += `<div class="admin-card"><h3 style="margin:0 0 12px;font-size:15px">改进建议（人审，不自动改）</h3>`;
    html += (data.suggestions||[]).map(s=>{
      const status = s.status || 'pending';
      let statusBadge = '';
      switch(status){
        case 'accepted':
          statusBadge = `<span class="suggestion-status accepted">已采纳 <a href="#" onclick="showTicketDetail(${s.ticket_id})">#${s.ticket_id}→</a></span>`;
          break;
        case 'rejected':
          statusBadge = `<span class="suggestion-status rejected">已驳回</span>`;
          break;
        case 'hold':
          statusBadge = `<span class="suggestion-status hold">存疑</span>`;
          break;
        default:
          statusBadge = `<span class="suggestion-status pending">待处理</span>`;
      }
      
      const buttons = status === 'pending' 
        ? `
          <button class="btn btn-primary btn-sm" onclick="openAdoptModal('${s.id}')">采纳→生成工单</button>
          <button class="btn btn-sm btn-danger" onclick="openRejectModal('${s.id}')">驳回</button>
          <button class="btn btn-sm" onclick="holdSuggestion('${s.id}')">存疑</button>
        `
        : '';
      
      return `
        <div style="margin-bottom:12px;padding:12px;background:#f9f9f9;border-radius:6px;position:relative">
          <div style="position:absolute;top:8px;right:8px">${statusBadge}</div>
          <b>${global.escAi(s.title)}</b>
          <div class="muted">${global.escAi(s.change_target||'')}</div>
          ${buttons ? `<div style="margin-top:8px">${buttons}</div>` : ''}
        </div>
      `;
    }).join('');
    html += `</div>`;
    
    host.innerHTML = html;
  }catch(e){ 
    host.innerHTML = `<div class="admin-card">${global.escAi(e.message)}</div>`; 
  }
}
```

### 2. 添加辅助函数

```javascript
// 展开依据详情
function expandEvidence(findingId, event){
  event.preventDefault();
  const detailDiv = $('evidence-' + findingId);
  if(!detailDiv) return;
  
  if(detailDiv.style.display === 'none'){
    // 加载run_ids列表
    loadEvidenceRuns(findingId).then(runs => {
      detailDiv.innerHTML = `
        <div style="margin-top:8px;padding:10px;background:#f5f5f5;border-radius:4px">
          <b>依据Run列表</b>
          <div style="margin-top:8px;max-height:200px;overflow-y:auto">
            ${runs.map(r => `
              <div style="padding:6px 0;border-bottom:1px solid #ddd;font-size:12px">
                <b>run_id:</b> ${r.run_id}<br>
                <b>intent:</b> ${r.intent} | 
                <b>outcome:</b> ${r.outcome} | 
                <b>badcase:</b> ${r.badcase_reason || '无'}<br>
                <b>时间:</b> ${r.created_at}
              </div>
            `).join('')}
          </div>
        </div>
      `;
      detailDiv.style.display = 'block';
    });
  } else {
    detailDiv.style.display = 'none';
  }
}
global.expandEvidence = expandEvidence;

// 加载依据runs（mock）
async function loadEvidenceRuns(findingId){
  // 实际应调用 API: /admin/review/finding/{findingId}/runs
  // 返回格式: [{run_id, intent, outcome, badcase_reason, created_at}]
  return [
    {run_id: 'abc123...', intent: 'policy', outcome: 'success', badcase_reason: 'rag_zero_hit', created_at: '2026-05-27 10:30'},
    {run_id: 'def456...', intent: 'policy', outcome: 'success', badcase_reason: 'rag_zero_hit', created_at: '2026-05-27 11:15'},
  ];
}

// 打开采纳确认弹层
function openAdoptModal(suggestionId){
  // 加载建议详情
  loadSuggestionDetail(suggestionId).then(s => {
    const modal = $('adoptSuggestionModal');
    if(!modal) return;
    
    $('adoptSuggestionTitle').textContent = s.title;
    $('adoptSuggestionContent').textContent = s.content;
    $('adoptSuggestionEvidence').textContent = `依据 ${s.run_count} 个run（可展开查看）`;
    $('adoptSuggestionDraft').textContent = s.draft || '工单草稿：修改XX模块...';
    $('adoptSuggestionAssignee').textContent = '技术主管（固定）';
    
    // 绑定确认按钮
    $('confirmAdoptBtn').onclick = () => {
      adoptSuggestionConfirmed(suggestionId);
      global.closeModal('adoptSuggestionModal');
    };
    
    global.openModal('adoptSuggestionModal');
  });
}
global.openAdoptModal = openAdoptModal;

// 确认采纳建议
async function adoptSuggestionConfirmed(suggestionId){
  try{
    const data = await global.apiPost('/admin/review/suggestions/' + suggestionId + '/adopt', {});
    global.toast('已生成工单 #' + data.ticket_id);
    loadReviewPageWithFilter();  // 刷新页面
  }catch(e){
    global.toast('采纳失败：' + e.message, 'danger');
  }
}

// 打开驳回原因弹层
function openRejectModal(suggestionId){
  const modal = $('rejectSuggestionModal');
  if(!modal) return;
  
  $('rejectSuggestionReason').value = '';
  
  $('confirmRejectBtn').onclick = () => {
    const reason = $('rejectSuggestionReason').value.trim();
    if(!reason){
      global.toast('请填写驳回理由', 'danger');
      return;
    }
    rejectSuggestion(suggestionId, reason);
    global.closeModal('rejectSuggestionModal');
  };
  
  global.openModal('rejectSuggestionModal');
}
global.openRejectModal = openRejectModal;

// 驳回建议
async function rejectSuggestion(suggestionId, reason){
  try{
    await global.apiPost('/admin/review/suggestions/' + suggestionId + '/reject', {reason});
    global.toast('已驳回建议');
    loadReviewPageWithFilter();  // 刷新页面
  }catch(e){
    global.toast('驳回失败：' + e.message, 'danger');
  }
}

// 存疑
async function holdSuggestion(suggestionId){
  try{
    await global.apiPost('/admin/review/suggestions/' + suggestionId + '/hold', {});
    global.toast('已标记为存疑');
    loadReviewPageWithFilter();  // 刷新页面
  }catch(e){
    global.toast('操作失败：' + e.message, 'danger');
  }
}
global.holdSuggestion = holdSuggestion;
```

### 3. 添加HTML模态框

文件: `frontend/index.html`

在现有模态框后添加：

```html
<!-- 采纳建议确认弹层 -->
<div class="modal" id="adoptSuggestionModal">
  <div class="modal-dialog">
    <div class="modal-header">
      <div class="modal-title">采纳改进建议</div>
      <div class="modal-close" onclick="closeModal('adoptSuggestionModal')">✕</div>
    </div>
    <div class="modal-body">
      <div style="margin-bottom:12px">
        <b id="adoptSuggestionTitle"></b>
        <div id="adoptSuggestionContent" style="color:#666;margin-top:4px;font-size:13px"></div>
      </div>
      <div style="margin-bottom:12px;padding:10px;background:#f5f5f5;border-radius:4px">
        <div id="adoptSuggestionEvidence" style="font-size:13px"></div>
      </div>
      <div style="margin-bottom:12px">
        <b>工单草稿：</b>
        <div id="adoptSuggestionDraft" style="color:#666;margin-top:4px;font-size:13px;white-space:pre-wrap"></div>
      </div>
      <div style="margin-bottom:12px">
        <b>负责人：</b>
        <span id="adoptSuggestionAssignee" style="color:#666"></span>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="closeModal('adoptSuggestionModal')">取消</button>
      <button class="btn btn-primary" id="confirmAdoptBtn">生成工单</button>
    </div>
  </div>
</div>

<!-- 驳回建议弹层 -->
<div class="modal" id="rejectSuggestionModal">
  <div class="modal-dialog dialog-sm">
    <div class="modal-header">
      <div class="modal-title">驳回改进建议</div>
      <div class="modal-close" onclick="closeModal('rejectSuggestionModal')">✕</div>
    </div>
    <div class="modal-body">
      <label style="display:block;margin-bottom:8px;font-weight:500">驳回理由：</label>
      <select id="rejectSuggestionReason" class="btn" style="width:100%;margin-bottom:12px">
        <option value="">请选择理由</option>
        <option value="归因不准">归因不准</option>
        <option value="无可改进">无可改进</option>
        <option value="重复建议">重复建议</option>
        <option value="其他">其他</option>
      </select>
      <textarea id="rejectSuggestionNote" placeholder="补充说明（可选）" style="width:100%;min-height:80px;padding:8px;border:1px solid var(--bd);border-radius:4px;font-size:13px"></textarea>
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="closeModal('rejectSuggestionModal')">取消</button>
      <button class="btn btn-danger" id="confirmRejectBtn">确认驳回</button>
    </div>
  </div>
</div>
```

### 4. 添加「立即重新生成」按钮

修改 `frontend/index.html` 复盘报告页面顶部：

```html
<div style="display:flex;gap:12px;margin-bottom:16px;align-items:center;flex-wrap:wrap">
  <label style="display:flex;align-items:center;gap:6px;font-size:14px">
    <span style="color:var(--t2)">选择周期：</span>
    <select id="reviewWeekSelector" class="btn" style="min-width:180px">
      <option value="latest">最新一周</option>
    </select>
  </label>
  <button class="btn btn-primary" onclick="loadReviewPageWithFilter()">查看报告</button>
  
  <!-- 立即重新生成按钮（仅tech_super_admin可见） -->
  <button 
    class="btn btn-primary" 
    id="regenerateReportBtn" 
    onclick="regenerateReportNow()" 
    style="margin-left:auto;display:none">
    ⚡ 立即重新生成本周报告
  </button>
  
  <span style="color:var(--t3);font-size:13px;margin-left:auto">复盘 Agent 每周自动生成一次增量报告</span>
</div>

<script>
// 在loadReviewPage()中显示/隐藏重新生成按钮
function updateRegenerateButtonVisibility(){
  const btn = $('regenerateReportBtn');
  if(btn && global.AUTH.role === 'tech_super_admin'){
    btn.style.display = 'inline-flex';
  } else if(btn) {
    btn.style.display = 'none';
  }
}

// 立即重新生成报告
async function regenerateReportNow(){
  if(!confirm('确定要立即重新生成本周复盘报告吗？\n\n这将触发复盘 Agent 重新分析本周所有运行数据。')){
    return;
  }
  
  try{
    const data = await global.apiPost('/admin/review/regenerate', {week: 'current'});
    global.toast('已触发复盘报告重新生成，请稍后刷新查看');
    // 可以添加轮询逻辑检查生成状态
  }catch(e){
    global.toast('触发失败：' + e.message, 'danger');
  }
}
global.regenerateReportNow = regenerateReportNow;
</script>
```

---

## 🔌 后端 API 需求

复盘报告页面需要以下后端API：

### 1. 获取可用周期列表
```
GET /admin/review/available-periods

Response:
{
  "code": 0,
  "data": {
    "periods": [
      {"value": "2026-W22", "label": "最新一周 (5/28-6/3)"},
      {"value": "2026-W21", "label": "2026 第21周 (5/21-5/27)"}
    ]
  }
}
```

### 2. 获取复盘报告
```
GET /admin/review/report?week=2026-W22

Response:
{
  "code": 0,
  "data": {
    "period": "2026-05-21 ~ 2026-05-27",
    "metrics": {
      "total_qa": 1240,
      "down_rate": 0.03,
      "timeout_rate": 0.01,
      "rag_zero_rate": 0.05
    },
    "findings": [
      {
        "id": "f1",
        "type": "fact",  // or "hypothesis"
        "text": "12 例 RAG 0 命中集中在「考勤补卡」类制度问题",
        "hypothesis": "疑似知识库缺该制度文档（待人确认）",
        "run_count": 12,
        "run_ids": ["abc...", "def..."]
      }
    ],
    "suggestions": [
      {
        "id": "s1",
        "title": "补充考勤制度文档",
        "content": "...",
        "change_target": "KNOWLEDGE_BASE",
        "status": "pending",  // or "accepted", "rejected", "hold"
        "ticket_id": null,  // accepted时有值
        "draft": "添加考勤补卡制度文档...",
        "run_count": 12
      }
    ]
  }
}
```

### 3. 获取finding的依据runs
```
GET /admin/review/finding/{findingId}/runs

Response:
{
  "code": 0,
  "data": {
    "runs": [
      {
        "run_id": "abc123...",
        "intent": "policy",
        "outcome": "success",
        "badcase_reason": "rag_zero_hit",
        "created_at": "2026-05-27 10:30"
      }
    ]
  }
}
```

### 4. 采纳建议
```
POST /admin/review/suggestions/{suggestionId}/adopt

Response:
{
  "code": 0,
  "data": {
    "ticket_id": 12,
    "status": "accepted"
  }
}
```

### 5. 驳回建议
```
POST /admin/review/suggestions/{suggestionId}/reject
Body: {"reason": "归因不准", "note": "..."}

Response:
{
  "code": 0,
  "data": {
    "status": "rejected"
  }
}
```

### 6. 存疑
```
POST /admin/review/suggestions/{suggestionId}/hold

Response:
{
  "code": 0,
  "data": {
    "status": "hold"
  }
}
```

### 7. 立即重新生成报告
```
POST /admin/review/regenerate
Body: {"week": "current"}

Response:
{
  "code": 0,
  "data": {
    "job_id": "job_abc123",
    "status": "queued"
  }
}
```

---

## ✅ 验收清单

### 功能验收
- [ ] 每条改进建议有三个按钮（采纳/驳回/存疑）
- [ ] 点驳回弹出理由选择框
- [ ] 每条finding有「事实」或「推测」标签
- [ ] 「依据:N个run」可点击展开，显示run元信息
- [ ] 点采纳弹确认层，含建议详情/依据/工单草稿/负责人
- [ ] 确认后生成工单，状态变为accepted，显示工单链接
- [ ] 每条建议有status角标，颜色正确
- [ ] tech_super_admin可见「立即重新生成」按钮
- [ ] biz_super_admin不可见「立即重新生成」按钮

### UI/UX验收
- [ ] 标签颜色符合规范（事实绿色，推测橙色）
- [ ] Status角标颜色正确（pending灰/accepted绿/rejected灰/hold黄）
- [ ] 模态框居中显示，遮罩层半透明
- [ ] 展开依据后可正常滚动
- [ ] 所有按钮hover有反馈

### 隐私验收
- [ ] 依据run列表**不显示**query原文
- [ ] 仅显示元信息：run_id, intent, outcome, badcase_reason, 时间

---

**文档创建时间**: 2026-05-28 01:45 AM  
**预计实现时间**: 4-6小时  
**优先级**: P0（复盘Agent依赖）
