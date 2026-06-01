/* 权限重构 + 改进闭环 — 与 index.html 配合 */
(function(global){
  /** 薪资分类：与 index.html categoryTree 中 l1-4 / l3-4-* 一致 */
  const PAYROLL_CAT = 'l1-4';
  const PAYROLL_L3_PREFIX = 'l3-4-';
  global.PAYROLL_CAT = PAYROLL_CAT;
  global.PAYROLL_L3_PREFIX = PAYROLL_L3_PREFIX;

  /** 全局枚举 → 中文（禁止把 DB 英文码直接展示给用户） */
  const ENUM_LABELS = {
    role: {
      tech_super_admin: '技术超管',
      biz_super_admin: '业务超管',
      staff: '普通员工',
      agent: '智能体',
      hr_admin: 'HR 管理员',
      viewer: '访客',
      admin: '管理员',
    },
    ticket_status: {
      pending: '待处理',
      in_progress: '处理中',
      awaiting_gate: '待验证',
      released: '已上线',
      done: '已上线',
      rejected: '已驳回',
      deferred: '存疑',
      hold: '存疑',
    },
    suggestion_status: {
      pending: '未处理',
      accepted: '已采纳',
      rejected: '已驳回',
      hold: '已存疑',
    },
    assignee: {
      tech_super_admin: '技术主管',
      biz_super_admin: '—',
    },
    audit_entry: {
      '数据中台': '数据中台',
      '智能体': '智能体',
      data: '数据中台',
      agent: '智能体',
    },
    badcase_reason: {
      rag_zero_hit: 'RAG 0 命中',
      clarify: '澄清过多',
      user_down: '用户点踩',
      timeout: '超时',
      over_reject: '过度拒答',
    },
  };

  function enumLabel(group, code){
    if(code == null || code === '') return '—';
    const map = ENUM_LABELS[group] || {};
    return map[code] || map[String(code).toLowerCase()] || String(code);
  }
  global.enumLabel = enumLabel;

  function roleLabel(role){
    const base = enumLabel('role', role) || '未登录';
    if(role === 'biz_super_admin') return base + ' [🔑薪资]';
    return base;
  }
  global.roleLabel = roleLabel;

  function ticketStatusLabel(status){
    return enumLabel('ticket_status', status);
  }
  global.ticketStatusLabel = ticketStatusLabel;

  function assigneeLabel(assignee, assigneeLabelField){
    if(assigneeLabelField) return assigneeLabelField;
    return enumLabel('assignee', assignee) || assignee || '—';
  }
  global.assigneeLabel = assigneeLabel;

  function entryLabel(entry){
    return enumLabel('audit_entry', entry);
  }
  global.entryLabel = entryLabel;

  function suggestionStatusLabel(status){
    return enumLabel('suggestion_status', status);
  }
  global.suggestionStatusLabel = suggestionStatusLabel;

  function canViewPayrollNav(){
    // 新规格：只有业务超管可看薪资分类导览
    if(!global.AUTH.token) return false;
    return global.AUTH.role === 'biz_super_admin';
  }
  function canManageUsers(){ return global.AUTH.role === 'tech_super_admin'; }
  function canGrantPayroll(){ return false; }  // 新规格：薪资权岗位自带，无需授予
  function canViewPayrollAudit(){ return ['tech_super_admin','biz_super_admin'].includes(global.AUTH.role); }
  function canViewReview(){ return ['tech_super_admin','biz_super_admin'].includes(global.AUTH.role); }
  /** 复盘建议决策（采纳/驳回/存疑）：仅业务超管 */
  const LEGACY_AUTH_ROLE_MAP = {
    super_admin: 'tech_super_admin',
    hr_admin: 'biz_super_admin',
    admin: 'staff',
    viewer: 'staff',
  };
  function normalizeAuthRole(role){
    const r = String(role || '').trim();
    return LEGACY_AUTH_ROLE_MAP[r] || r || 'staff';
  }
  function syncAuthRoleFromStorage(){
    if(!global.AUTH) return;
    const stored = localStorage.getItem('hr_role');
    if(stored) global.AUTH.role = normalizeAuthRole(stored);
  }
  /** 复盘决策权：仅业务超管；并以接口 view_mode 为准（防缓存/旧 role） */
  function isReviewBizDecider(){
    if(global._reviewViewMode === 'tech_readonly') return false;
    if(global._reviewViewMode === 'biz_decision') return true;
    syncAuthRoleFromStorage();
    return normalizeAuthRole(global.AUTH && global.AUTH.role) === 'biz_super_admin';
  }
  function canDecideReview(){ return isReviewBizDecider(); }
  global.canDecideReview = canDecideReview;
  global.isReviewBizDecider = isReviewBizDecider;

  function formatDraftChanges(dc){
    if(!dc) return '—';
    const parts = [];
    if(dc.target) parts.push('改动：'+dc.target);
    if(dc.action) parts.push('方案：'+dc.action);
    if(dc.add_test_case) parts.push('测试：'+dc.add_test_case);
    return parts.length ? parts.join(' · ') : '—';
  }
  global.formatDraftChanges = formatDraftChanges;

  function ticketDisplayText(t, mine){
    if(mine || !isReviewBizDecider()){
      return t.display_body || formatDraftChanges(t.draft_changes) || t.content_biz || t.title || '—';
    }
    return t.content_biz || t.title || '—';
  }

  function canViewEval(){ return global.AUTH.role === 'tech_super_admin'; }
  function canTrackTickets(){ return isReviewBizDecider(); }
  function canOperateTickets(){ return global.AUTH.role === 'tech_super_admin'; }
  function isPayrollL3(id){ return String(id||'').startsWith(PAYROLL_L3_PREFIX); }

  function filterCategoryTree(tree){
    if(!Array.isArray(tree)) return [];
    // 新规格：不过滤薪资分类，而是标记为disabled让renderTree置灰
    return tree.map(l1 => {
      if(l1.id === PAYROLL_CAT && !canViewPayrollNav()){
        return {...l1, disabled: true};
      }
      return l1;
    });
  }
  global.filterCategoryTree = filterCategoryTree;

  function apiHeaders(extra={}, opts={}){
    const h = {...extra};
    if(!opts.skipJson) h['Content-Type'] = 'application/json';
    if(global.AUTH.token) h['Authorization'] = 'Bearer '+global.AUTH.token;
    if(global.AUTH.payrollConfirmToken) h['X-Payroll-Confirm'] = global.AUTH.payrollConfirmToken;
    return h;
  }
  global.apiHeaders = apiHeaders;

  async function authLogin(username, password){
    const data = await global.apiPost('/auth/login', {username, password});
    
    // 更新 AUTH 状态
    global.AUTH.token = data.access_token;
    global.AUTH.role = normalizeAuthRole(data.role);
    global.AUTH.username = username;
    global.AUTH.displayName = data.display_name || username;
    global.AUTH.employeeId = data.employee_id || '';
    global.AUTH.payrollAccess = !!data.payroll_access;
    global.AUTH.mustChangePassword = !!data.must_change_password;
    global.AUTH.payrollConfirmToken = '';
    
    // 持久化到 localStorage
    localStorage.setItem('hr_token', global.AUTH.token);
    localStorage.setItem('hr_role', global.AUTH.role);
    localStorage.setItem('hr_username', username);
    localStorage.setItem('hr_display_name', global.AUTH.displayName);
    localStorage.setItem('hr_payroll_access', global.AUTH.payrollAccess ? '1' : '');
    
    // 更新 UI
    global.renderAuthBar && global.renderAuthBar();
    global.renderAdminNav && global.renderAdminNav();
    global.syncAuthGate && global.syncAuthGate();
    global.closeModal && global.closeModal('loginModal');
    // 注意：renderUserDropdown 会在 renderAuthBar 之后自动调用
    
    // 提示
    global.toast && global.toast('已登录：'+(global.AUTH.displayName||username)+' · '+roleLabel(global.AUTH.role));
    return data;
  }
  global.authLogin = authLogin;

  function authLogout(){
    // 清理所有 AUTH 状态
    global.AUTH.token = ''; 
    global.AUTH.role = ''; 
    global.AUTH.username = ''; 
    global.AUTH.displayName = '';
    global.AUTH.payrollAccess = false; 
    global.AUTH.payrollConfirmToken = ''; 
    global.AUTH.payrollConfirmedUntil = 0;  // 重置TTL
    global.AUTH.payrollConfirmReason = '';  // 清除事由
    global.AUTH.employeeId = '';
    global.AUTH.mustChangePassword = false;
    
    // 清理 localStorage
    localStorage.removeItem('hr_token'); 
    localStorage.removeItem('hr_role'); 
    localStorage.removeItem('hr_username');
    localStorage.removeItem('hr_display_name'); 
    localStorage.removeItem('hr_payroll_access');
    
    // 更新 UI（必须在 syncAuthGate 之前）
    global.renderAuthBar && global.renderAuthBar();
    global.renderAdminNav && global.renderAdminNav();
    
    // 触发认证门禁（弹出登录框）
    global.syncAuthGate && global.syncAuthGate();
    
    // 提示信息
    global.toast && global.toast('已退出，请重新登录');
  }
  global.authLogout = authLogout;

  let payrollConfirmResolver = null;
  let payrollConfirmContext = null;  // 保存完整上下文
  function openPayrollConfirmModal(ctx){
    payrollConfirmContext = ctx;  // 保存上下文（包含target_ref, entry, fields）
    $('payrollConfirmTarget').textContent = ctx.target_ref || '';
    $('payrollConfirmEntry').textContent = ctx.entry || '';
    $('payrollConfirmReason').value = '';
    global.openModal('payrollConfirmModal');
    return new Promise(resolve => { payrollConfirmResolver = resolve; });
  }
  global.openPayrollConfirmModal = openPayrollConfirmModal;  // 暴露到全局
  
  function cancelPayrollConfirm(){
    global.closeModal('payrollConfirmModal');
    if(payrollConfirmResolver) payrollConfirmResolver(false);
    payrollConfirmResolver = null;
  }
  global.cancelPayrollConfirm = cancelPayrollConfirm;
  
  async function submitPayrollConfirm(){
    const reason = ($('payrollConfirmReason').value||'').trim();
    if(!reason){ global.toast('请填写访问事由'); return; }
    const ctx = payrollConfirmContext || {};
    console.log('[薪资确认] 提交确认，上下文:', ctx);
    try{
      const data = await global.apiPost('/admin/payroll/confirm-access', {
        target_ref: ctx.target_ref || '',
        entry: ctx.entry || '',
        fields: ctx.fields || '',  // 使用上下文中的fields，而不是重复entry
        reason
      });
      console.log('[薪资确认] 后端返回:', data);
      global.AUTH.payrollConfirmToken = data.confirm_token;
      global.AUTH.payrollConfirmReason = reason;  // 保存事由，TTL期内复用
      console.log('[薪资确认] Token已保存:', global.AUTH.payrollConfirmToken);
      global.closeModal('payrollConfirmModal');
      if(payrollConfirmResolver) payrollConfirmResolver(true);
      payrollConfirmResolver = null;
      global.toast('已确认，30分钟内访问薪资无需重复确认');
    }catch(e){ 
      console.error('[薪资确认] 失败:', e);
      global.toast('确认失败：'+e.message); 
    }
  }
  global.submitPayrollConfirm = submitPayrollConfirm;

  async function ensurePayrollAccess(ctx){
    // 新规格：只有业务超管可访问薪资
    if(global.AUTH.role !== 'biz_super_admin') return false;
    
    // 检查30分钟TTL：未过期直接放行
    const now = Date.now();
    if(global.AUTH.payrollConfirmedUntil > now){
      return true;  // TTL内，免弹
    }
    
    // TTL外或首次访问，弹出二次确认
    const ok = await openPayrollConfirmModal(ctx);
    if(ok){
      // 确认成功，设置30分钟TTL
      global.AUTH.payrollConfirmedUntil = now + 30 * 60 * 1000;  // 30分钟
      // 事由由submitPayrollConfirm存入AUTH.payrollConfirmReason
    }
    return !!ok;
  }
  global.ensurePayrollAccess = ensurePayrollAccess;

  function renderAdminNav(){
    // 所有管理功能已整合到用户下拉框，外部不再显示独立 tab
    const el = $('adminNav'); 
    if(el) el.innerHTML = '';
  }
  global.renderAdminNav = renderAdminNav;

  function renderUserDropdown(){
    const dropdown = $('userDropdown');
    if(!dropdown || !global.AUTH.token) return;
    const items = [];
    
    // 用户管理（仅超级管理员）
    if(canManageUsers()){
      items.push(`<div class="user-dropdown-item" onclick="closeDropdownAndGo('users')">
        <svg class="user-dropdown-icon-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
          <circle cx="9" cy="7" r="4"></circle>
          <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
          <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
        </svg>
        用户管理
      </div>`);
    }
    
    // 薪资访问审计（仅 biz_super_admin）
    if(canViewPayrollAudit()){
      items.push(`<div class="user-dropdown-item" onclick="closeDropdownAndGo('payroll-audit')">
        <svg class="user-dropdown-icon-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
        </svg>
        薪资访问审计
      </div>`);
    }
    
    // 复盘报告
    if(canViewReview()){
      items.push(`<div class="user-dropdown-item" onclick="closeDropdownAndGo('review')">
        <svg class="user-dropdown-icon-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 11l3 3L22 4"></path>
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
        </svg>
        复盘报告
      </div>`);
    }

    // 评测中心：仅技术超管（业务超管不可见）
    if(canViewEval()){
      items.push(`<div class="user-dropdown-item" onclick="closeDropdownAndGo('eval')">
        <svg class="user-dropdown-icon-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 20V10"></path>
          <path d="M18 20V4"></path>
          <path d="M6 20v-4"></path>
        </svg>
        评测中心
      </div>`);
    }
    
    // 改进工单追踪（仅业务超管；技术超管用「我的工单」工作台）
    if(canTrackTickets()){
      items.push(`<div class="user-dropdown-item" onclick="closeDropdownAndGo('tickets')">
        <svg class="user-dropdown-icon-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2"></rect>
          <line x1="9" y1="3" x2="9" y2="21"></line>
        </svg>
        改进工单追踪
      </div>`);
    }
    
    // 我的工单（tech_super_admin）
    if(canOperateTickets()){
      items.push(`<div class="user-dropdown-item" onclick="closeDropdownAndGo('my-tickets')">
        <svg class="user-dropdown-icon-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
          <circle cx="8.5" cy="7" r="4"></circle>
          <polyline points="17 11 19 13 23 9"></polyline>
        </svg>
        我的工单
      </div>`);
    }
    
    // 退出：始终显示，功能项存在时加分隔线
    if(items.length > 0){
      items.push(`<div class="user-dropdown-divider"></div>`);
    }
    items.push(`<div class="user-dropdown-item danger" onclick="closeDropdownAndLogout()">
      <svg class="user-dropdown-icon-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
        <polyline points="16 17 21 12 16 7"></polyline>
        <line x1="21" y1="12" x2="9" y2="12"></line>
      </svg>
      退出
    </div>`);

    dropdown.innerHTML = items.join('');
  }
  global.renderUserDropdown = renderUserDropdown;

  function closeDropdownAndGo(page){
    const dropdown = $('userDropdown');
    if(dropdown) dropdown.classList.remove('show');
    switchAdminPage(page);
  }
  global.closeDropdownAndGo = closeDropdownAndGo;

  function closeDropdownAndLogout(){
    const dropdown = $('userDropdown');
    if(dropdown) dropdown.classList.remove('show');
    global.authLogout();
  }
  global.closeDropdownAndLogout = closeDropdownAndLogout;

  function switchAdminPage(page){
    global.switchMode && global.switchMode('admin');

    // 权限前置检查：不通过则不激活 pane，直接返回
    if(page === 'tickets' && !canTrackTickets()){
      global.toast('改进工单追踪仅业务超管可见');
      return;
    }
    if(page === 'eval' && !canViewEval()){
      global.toast('无权限访问评测中心');
      return;
    }

    document.querySelectorAll('.admin-pane').forEach(p => p.classList.remove('active'));
    const pane = $('admin-' + page);
    if(pane) pane.classList.add('active');
    // 离开复盘页时隐藏浮条并清除导航状态
    if(page !== 'review'){
      global.hideBackFloatTickets && global.hideBackFloatTickets();
      global._reviewNavReturn   = null;
      global._pendingReviewWeek = null;
    }

    if(page === 'users') loadUsersPage();
    if(page === 'payroll-audit') loadPayrollAuditPage();
    if(page === 'review'){ syncAuthRoleFromStorage(); loadReviewPage(); }
    if(page === 'eval') loadEvalPage();
    if(page === 'tickets') loadTicketsPage(false);
    if(page === 'my-tickets') loadTicketsPage(true);
  }
  global.switchAdminPage = switchAdminPage;

  async function loadUsersPage(){
    const host = $('adminUsersBody'); if(!host) return;
    try{
      const data = await global.apiGet('/admin/users');
      host.innerHTML = (data.items||[]).map(u=>{
        // 新规格：移除薪资权限列，薪资权由角色决定
        const ops = canManageUsers()&&u.role!=='tech_super_admin'
          ? `<button class="btn btn-sm btn-detail" onclick="editUserPrompt('${global.escAi(u.username)}','${global.escAi(u.role||'')}','${global.escAi(u.display_name||'')}',${u.is_active?1:0})">编辑</button>`
          : '—';
        const roleDisp = u.role_label || enumLabel('role', u.role);
        return `<tr><td>${global.escAi(u.display_name)}</td><td>${global.escAi(u.employee_id||'—')}</td><td>${global.escAi(roleDisp)}</td><td>${u.is_active?'启用':'停用'}</td><td>${ops}</td></tr>`;
      }).join('');
    }catch(e){ host.innerHTML=`<tr><td colspan="5">${global.escAi(e.message)}</td></tr>`; }
  }

  // 移除发证页加载函数（新规格：薪资权岗位自带）

  async function loadPayrollAuditPage(){
    const host = $('adminPayrollAuditBody'); if(!host) return;
    try{
      const data = await global.apiGet('/admin/payroll/access-logs');
      host.innerHTML = (data.items||[]).map(r=>`<tr><td>${global.escAi((r.created_at||'').replace('T',' ').slice(0,16))}</td><td>${global.escAi(r.actor)}</td><td>${global.escAi(r.target_ref)}</td><td>${entryLabel(r.entry)}</td><td>${global.escAi(r.fields)}</td><td>${global.escAi(r.reason)}</td></tr>`).join('');
    }catch(e){ host.innerHTML=`<tr><td colspan="6">${global.escAi(e.message)}</td></tr>`; }
  }

  async function loadReviewPage(){
    syncAuthRoleFromStorage();
    applyReviewLayoutMode();
    updateReviewReadonlyBanner();
    const selector = $('reviewWeekSelector');
    if(selector){
      try{
        const data = await global.apiGet('/admin/review/available-periods');
        const periods = data.periods || [];
        const options = [`<option value="all">全部报告</option>`];
        periods.forEach(p => {
          options.push(`<option value="${global.escAi(p.value)}">${global.escAi(p.label)}</option>`);
        });
        selector.innerHTML = options.join('');
        // 应用跳转预设的周期（jumpToReportWeek 传入）
        if(global._pendingReviewWeek){
          selector.value = global._pendingReviewWeek;
          global._pendingReviewWeek = null;
        }
      }catch(e){
        selector.innerHTML = `<option value="all" selected>全部报告</option>`;
      }
    }
    loadReviewPageWithFilter();
  }

  function renderReviewMetric(label, value){
    return `<div class="rv-metric"><div class="rv-metric-label">${label}</div><div class="rv-metric-value">${value}</div></div>`;
  }

  const REVIEW_TECH_READONLY_HINT =
    '复盘报告对技术超管为只读。决策由业务超管操作；被采纳的建议生成工单后，你在「我的工单」工作台处理。';

  function reviewPriorityLabel(p){
    const m = { high: '高', medium: '中', low: '低' };
    return m[String(p||'').toLowerCase()] || p || '—';
  }

  function renderReviewFindingBiz(f){
    const alertBlock = f.recurring_alert
      ? `<div class="rv-finding-alert">⚠ ${global.escAi(f.recurring_alert)}</div>` : '';
    const warn = f.biz_problem_valid === false
      ? `<div class="rv-finding-warn">⚠ 业务摘要含技术用语，需复盘 Agent 重写</div>` : '';
    return `
      <div class="rv-finding">
        ${alertBlock}${warn}
        <div class="rv-finding-text">${global.escAi(f.biz_problem||'')}</div>
        <div class="rv-finding-sub">${global.escAi(f.impact||'')} · 优先级 ${reviewPriorityLabel(f.priority)}</div>
      </div>`;
  }

  function renderReviewFindingTech(f){
    const tech = f.technical || {};
    const runIds = tech.run_ids || f.evidence_run_ids || f.run_ids || [];
    const nodes = tech.agent_nodes || [];
    return `
      <div class="rv-finding rv-finding-tech-view">
        <div class="rv-finding-text">${global.escAi(tech.phenomenon || f.phenomenon || '')}</div>
        <div class="rv-finding-sub">${global.escAi(tech.root_cause_hypothesis || f.root_cause_hypothesis || '')}</div>
        <div class="rv-finding-tech">
          <div class="rv-finding-tech-title">技术线索</div>
          ${(tech.node_clues || f.node_clues) ? `<div class="rv-finding-tech-row"><span class="rv-tech-label">节点线索</span><span>${global.escAi(tech.node_clues || f.node_clues)}</span></div>` : ''}
          ${nodes.length ? `<div class="rv-finding-tech-row"><span class="rv-tech-label">Agent 节点</span><span>${nodes.map(n => global.escAi(n)).join(' → ')}</span></div>` : ''}
          ${runIds.length ? `<div class="rv-finding-tech-row"><span class="rv-tech-label">run_id</span><code class="rv-run-ids">${runIds.map(r => global.escAi(r)).join(', ')}</code></div>` : ''}
          ${tech.trace_hint ? `<div class="rv-finding-tech-hint">${global.escAi(tech.trace_hint)}</div>` : ''}
        </div>
      </div>`;
  }

  function renderReviewFinding(f, techView){
    return techView ? renderReviewFindingTech(f) : renderReviewFindingBiz(f);
  }

  function renderReviewReport(rep){
    const bizDecide = isReviewBizDecider();
    const m = rep.metrics || {};
    const findings = rep.findings || [];
    const suggestions = rep.suggestions || [];

    const metricsHtml = `
      <div class="rv-metrics">
        ${renderReviewMetric('总问答', m.total_qa || 0)}
        ${renderReviewMetric('👎率', ((m.down_rate||0)*100).toFixed(1) + '%')}
        ${renderReviewMetric('超时率', ((m.timeout_rate||0)*100).toFixed(1) + '%')}
        ${renderReviewMetric('RAG0命中', ((m.rag_zero_rate||0)*100).toFixed(1) + '%')}
      </div>`;

    const findingsHtml = findings.length ? `
      <div class="rv-section">
        <div class="rv-section-title">${bizDecide ? '问题归类与归因' : '问题归类与归因（含技术线索）'}</div>
        ${findings.map(f => renderReviewFinding(f, !bizDecide)).join('')}
      </div>` : '';

    const sugTitle = bizDecide
      ? '改进建议（人审，不自动改）'
      : '改进建议（只读 · 待业务超管决策）';
    const suggestionsHtml = suggestions.length ? `
      <div class="rv-section">
        <div class="rv-section-title">${sugTitle}</div>
        ${suggestions.map(s => renderSuggestionBlock(s, rep)).join('')}
      </div>` : '';

    const genAt = rep.generated_at ? ' · 生成于 ' + global.escAi(String(rep.generated_at).replace('T',' ').slice(0,16)) : '';
    return `
      <div class="rv-report">
        <div class="rv-report-head">
          <div class="rv-report-title">${global.escAi(rep.label || rep.period || '')}</div>
          <div class="rv-report-meta">${global.escAi(rep.period || '')}${genAt}</div>
        </div>
        ${metricsHtml}
        ${findingsHtml}
        ${suggestionsHtml}
      </div>`;
  }

  function renderSuggestionBlockTech(s, rep){
    const rid = global.escAi(rep && rep.id || '');
    const st = s.status || 'pending';
    let statusHtml = '';
    if(st === 'accepted' && s.ticket_id != null){
      const tno = '#' + String(s.ticket_id).padStart(3,'0');
      statusHtml = `<div class="rv-suggestion-status accepted">
        ✓ 已采纳并生成工单 <span class="action-link" onclick="openTicketFromReview(${s.ticket_id},'${rid}')">${global.escAi(tno)} →</span>
        <span class="rv-suggestion-hint">请在「我的工单」中处理</span>
      </div>`;
    } else if(st === 'rejected'){
      statusHtml = `<div class="rv-suggestion-status muted-ro">业务超管已驳回</div>`;
    } else if(st === 'hold'){
      statusHtml = `<div class="rv-suggestion-status muted-ro">业务超管已标记存疑</div>`;
    } else {
      statusHtml = `<div class="rv-suggestion-status muted-ro">待业务超管决策</div>`;
    }
    return `<div class="rv-suggestion rv-suggestion-readonly">
      <div class="rv-suggestion-title">${global.escAi(s.draft_summary || formatDraftChanges(s.draft_changes))}</div>
      ${statusHtml}
    </div>`;
  }

  function applyReviewLayoutMode(){
    const layout = $('reviewLayout');
    const sidebar = $('reviewHoldSidebar');
    const biz = isReviewBizDecider();
    if(layout){
      layout.classList.toggle('tech-readonly', !biz);
      layout.classList.add('no-sidebar');
      if(biz) layout.classList.remove('no-sidebar');
    }
    if(sidebar){
      sidebar.hidden = true;
      sidebar.style.display = 'none';
      sidebar.setAttribute('aria-hidden', 'true');
      if(!biz){
        sidebar.innerHTML = '';
      }
    }
  }

  function renderSuggestionBlock(s, rep){
    if(!isReviewBizDecider()){
      return renderSuggestionBlockTech(s, rep);
    }
    const rid = global.escAi(rep.id||'');
    const sid = global.escAi(s.id||'');
    const st = s.status || 'pending';
    let actions = '';

    if(st === 'pending' || !st){
      actions = `<div class="rv-suggestion-actions">
        <button class="btn btn-primary btn-sm" onclick="adoptSuggestion('${sid}','${rid}')">采纳→生成工单</button>
        <button class="btn btn-sm" onclick="rejectSuggestion('${sid}','${rid}')">驳回</button>
        <button class="btn btn-sm" onclick="holdSuggestion('${sid}','${rid}')">存疑</button>
      </div>`;
    } else if(st === 'accepted'){
      const tno = s.ticket_id != null ? ('#' + String(s.ticket_id).padStart(3,'0')) : '';
      actions = `<div class="rv-suggestion-status accepted">
        ✓ 已生成工单 <span class="action-link" onclick="openTicketFromReview(${s.ticket_id},'${rid}')">${global.escAi(tno)} →</span>
      </div>`;
    } else if(st === 'rejected'){
      const reason = s.reject_reason || '无驳回理由';
      actions = `<div class="rv-suggestion-status rejected">
        ✕ 已驳回 <span class="action-link" data-reject-reason="${global.escAi(reason)}" onclick="showRejectReason(this)">查看理由</span>
      </div>`;
    } else if(st === 'hold'){
      actions = `<div class="rv-suggestion-status hold">⏸ 已存疑</div>`;
    }
    return `<div class="rv-suggestion">
      <div class="rv-suggestion-title">${global.escAi(s.content_biz||'')}</div>
      ${actions}
    </div>`;
  }

  const _holdItemsCache = {};

  async function loadReviewHoldSidebar(){
    applyReviewLayoutMode();
    if(!isReviewBizDecider()) return;

    const sidebar = $('reviewHoldSidebar');
    const layout = $('reviewLayout');
    const listHost = $('reviewHoldList');
    const badge = $('reviewHoldBadge');
    if(!sidebar || !listHost) return;
    Object.keys(_holdItemsCache).forEach(k => delete _holdItemsCache[k]);
    sidebar.hidden = false;
    sidebar.style.display = '';
    sidebar.removeAttribute('aria-hidden');
    try{
      const data = await global.apiGet('/admin/review/hold-pending');
      const items = data.items || [];
      if(badge) badge.textContent = String(items.length);
      if(!items.length){
        listHost.innerHTML = '<div class="muted" style="font-size:12px">暂无存疑项</div>';
      } else {
        listHost.innerHTML = items.map(it => {
          _holdItemsCache[it.suggestion_id] = it;
          const sid = global.escAi(it.suggestion_id);
          const rid = global.escAi(it.report_id);
          return `
          <div class="rv-hold-item">
            <div class="rv-hold-item-title">${global.escAi(it.content_biz||'')}</div>
            <div class="rv-hold-item-meta">来自 ${global.escAi(it.report_label||it.report_week||'')} · 已挂起 ${it.hold_weeks||1} 周</div>
            <div class="rv-suggestion-actions">
              <button class="btn btn-primary btn-sm" onclick="readoptHoldById('${sid}')">重新采纳</button>
              <button class="btn btn-sm" onclick="rejectHoldSuggestion('${sid}','${rid}')">驳回</button>
            </div>
          </div>`;
        }).join('');
      }
      sidebar.style.display = 'block';
      if(layout) layout.classList.remove('no-sidebar');
    }catch(e){
      listHost.innerHTML = `<div class="rv-empty-error" style="padding:8px;font-size:12px">${global.escAi(e.message)}</div>`;
    }
  }

  function updateReviewReadonlyBanner(){
    const el = $('reviewReadonlyBanner');
    if(!el) return;
    if(isReviewBizDecider()){
      el.style.display = 'none';
      el.textContent = '';
    } else {
      el.style.display = 'block';
      el.textContent = REVIEW_TECH_READONLY_HINT;
    }
  }

  async function loadReviewPageWithFilter(){
    const host = $('adminReviewBody'); if(!host) return;
    const selector = $('reviewWeekSelector');
    const selectedWeek = selector ? selector.value : 'all';
    const periodSpan = $('reviewPeriod');
    updateReviewReadonlyBanner();

    host.innerHTML = `<div class="rv-empty">正在加载报告…</div>`;

    try{
      const data = await global.apiGet('/admin/review/report', {week: selectedWeek});
      global._reviewViewMode = data.view_mode || null;
      applyReviewLayoutMode();
      updateReviewReadonlyBanner();
      const items = data.items || [];

      if(periodSpan){
        if(selectedWeek === 'all'){
          periodSpan.textContent = `共 ${items.length} 份`;
        }else if(items.length){
          periodSpan.textContent = items[0].period || '';
        }else{
          periodSpan.textContent = '';
        }
      }

      if(!items.length){
        host.innerHTML = `<div class="rv-empty">该周期暂无复盘报告</div>`;
        global._reviewReportsCache = [];
        await loadReviewHoldSidebar();
        return;
      }

      global._reviewReportsCache = items;
      host.innerHTML = items.map(renderReviewReport).join('');
      await loadReviewHoldSidebar();
    }catch(e){
      host.innerHTML = `<div class="rv-empty rv-empty-error">${global.escAi(e.message)}</div>`;
    }
  }
  global.loadReviewPageWithFilter = loadReviewPageWithFilter;

  function ticketStatusBadge(status){
    const map = {
      pending: 'tk-st-pending',
      in_progress: 'tk-st-progress',
      awaiting_gate: 'tk-st-gate',
      released: 'tk-st-done',
      done: 'tk-st-done',
      rejected: 'tk-st-rejected',
      deferred: 'tk-st-hold',
      hold: 'tk-st-hold',
    };
    const cls = map[status] || 'tk-st-default';
    return `<span class="tk-status ${cls}">${global.escAi(ticketStatusLabel(status))}</span>`;
  }

  function formatTicketNotesCell(t){
    const notes = t.notes || [];
    if(!notes.length){
      return '<span class="muted">—</span>';
    }
    const last = notes[notes.length - 1];
    const raw = String(last.content || '');
    const preview = raw.length > 36 ? raw.slice(0, 36) + '…' : raw;
    const countHint = notes.length > 1 ? `<span class="muted"> (${notes.length}条)</span>` : '';
    return `<span class="ticket-note-preview" title="${global.escAi(raw)}">${global.escAi(preview)}${countHint}</span>`;
  }

  function ticketRowOps(t, mine){
    const st = t.status;
    let ops = `<button class="btn btn-sm btn-detail" onclick="showTicketDetail(${t.id})">详情</button>`;
    const canNote = st !== 'rejected';
    if(canNote && !mine && isReviewBizDecider()){
      ops += ` <button class="btn btn-sm btn-detail" onclick="openTicketNoteEditor(${t.id})">编辑</button>`;
    }
    if(!mine && isReviewBizDecider() && st === 'pending'){
      ops += ` <button class="btn btn-sm btn-reject-ticket" onclick="withdrawTicket(${t.id})">撤回</button>`;
    }
    if(mine && canOperateTickets()){
      if(st === 'pending'){
        ops += ` <button class="btn btn-sm btn-accept" onclick="ticketAccept(${t.id})">接单</button>`;
        ops += ` <button class="btn btn-sm btn-reject-ticket" onclick="ticketReject(${t.id})">驳回</button>`;
      } else if(st === 'in_progress'){
        ops += ` <button class="btn btn-sm btn-complete" onclick="ticketComplete(${t.id})">标记完成</button>`;
        ops += ` <button class="btn btn-sm btn-reject-ticket" onclick="ticketReject(${t.id})">驳回</button>`;
      } else if(st === 'awaiting_gate'){
        ops += ` <button class="btn btn-sm btn-release" onclick="ticketRelease(${t.id})">门禁通过·确认上线</button>`;
      }
    }
    return ops;
  }

  async function loadTicketsPage(mine, statusOverride){
    const host = $(mine ? 'adminMyTicketsBody' : 'adminTicketsBody');
    if(!host) return;
    const filterEl = $(mine ? 'myTicketsStatusFilter' : 'ticketsStatusFilter');
    const hintEl  = $(mine ? 'myTicketsResultHint'  : 'ticketsResultHint');
    const status  = statusOverride !== undefined ? statusOverride : (filterEl ? filterEl.value : '');
    const cols    = mine ? 6 : 7;
    host.innerHTML = `<tr><td colspan="${cols}" class="muted" style="text-align:center;padding:20px">加载中…</td></tr>`;
    if(hintEl) hintEl.textContent = '';
    const params = { mine: mine ? 'true' : 'false' };
    if(status) params.status = status;
    try{
      const data = await global.apiGet('/admin/tickets', params);
      const items = data.items || [];
      if(hintEl){
        hintEl.textContent = status
          ? `筛选「${global.escAi(ticketStatusLabel(status))}」共 ${items.length} 条`
          : `共 ${items.length} 条`;
      }
      if(!items.length){
        host.innerHTML = `<tr><td colspan="${cols}" class="muted" style="text-align:center;padding:28px">暂无符合条件的工单</td></tr>`;
        return;
      }
      host.innerHTML = items.map(t => {
        const ops = ticketRowOps(t, mine);
        const noteCell = formatTicketNotesCell(t);
        const label = ticketDisplayText(t, mine);
        const noLink = `<span class="action-link tkt-no-link" onclick="showTicketDetail(${t.id})">${global.escAi(t.ticket_no)}</span>`;
        if(mine){
          return `<tr><td>${noLink}</td><td>${global.escAi(label)}</td><td>${global.escAi(t.source)}</td><td>${ticketStatusBadge(t.status)}</td><td>${noteCell}</td><td>${ops}</td></tr>`;
        }
        return `<tr><td>${noLink}</td><td class="tk-cell-biz">${global.escAi(label)}</td><td>${global.escAi(t.source)}</td><td>${ticketStatusBadge(t.status)}</td><td>${global.escAi(assigneeLabel(t.assignee, t.assignee_label))}</td><td>${noteCell}</td><td>${ops}</td></tr>`;
      }).join('');
    }catch(e){
      host.innerHTML = `<tr><td colspan="${cols}" style="color:#c53030">${global.escAi(e.message)}</td></tr>`;
    }
  }
  global.loadTicketsPage = loadTicketsPage;

  global.applyTicketsFilter = function(mine){
    if(!mine && !canTrackTickets()){ global.toast('改进工单追踪仅业务超管可见'); return; }
    if(mine && !canOperateTickets()){ global.toast('无权限'); return; }
    loadTicketsPage(mine);
  };

  global.clearTicketsFilter = function(mine){
    if(!mine && !canTrackTickets()){ global.toast('改进工单追踪仅业务超管可见'); return; }
    const filterEl = $(mine ? 'myTicketsStatusFilter' : 'ticketsStatusFilter');
    if(filterEl) filterEl.value = '';
    loadTicketsPage(mine, '');
  };

  global.rejectSuggestion = async function(id, reportId){
    if(!isReviewBizDecider()){ global.toast('复盘决策仅业务超管可操作'); return; }
    const reason = prompt('驳回理由（必填）');
    if(!reason || !reason.trim()) return;
    try{
      await global.apiPost('/admin/review/suggestions/'+encodeURIComponent(id)+'/reject?report_id='+encodeURIComponent(reportId||''), {reason: reason.trim()});
      global.toast('已驳回'); loadReviewPage();
    }catch(e){ global.toast(e.message); }
  };

  global.holdSuggestion = async function(id, reportId){
    if(!isReviewBizDecider()){ global.toast('复盘决策仅业务超管可操作'); return; }
    try{
      await global.apiPost('/admin/review/suggestions/'+encodeURIComponent(id)+'/hold?report_id='+encodeURIComponent(reportId||''), {});
      global.toast('已标记存疑'); loadReviewPage();
    }catch(e){ global.toast(e.message); }
  };

  global.showRejectReason = function(el){
    const reason = (el && el.getAttribute('data-reject-reason')) || '无驳回理由';
    alert(reason);
  };

  global.readoptHoldById = function(suggestionId){
    if(!isReviewBizDecider()) return;
    const it = _holdItemsCache[suggestionId];
    if(!it){ global.toast('存疑项已刷新，请重试'); return; }
    readoptHoldSuggestion(it);
  };

  global.readoptHoldSuggestion = async function(holdItem){
    const it = typeof holdItem === 'string' ? JSON.parse(holdItem) : holdItem;
    try{
      await global.apiPost('/admin/review/suggestions/'+encodeURIComponent(it.suggestion_id)+'/readopt', {
        suggestion_id: it.suggestion_id,
        content_biz: it.content_biz,
        evidence_run_ids: it.evidence_run_ids||[],
        report_id: it.report_id,
      });
      global.toast('已重新采纳并生成工单'); loadReviewPage(); loadTicketsPage(false);
    }catch(e){ global.toast(e.message); }
  };

  global.rejectHoldSuggestion = async function(id, reportId){
    if(!isReviewBizDecider()){ global.toast('复盘决策仅业务超管可操作'); return; }
    const reason = prompt('驳回理由（必填）');
    if(!reason || !reason.trim()) return;
    try{
      await global.apiPost('/admin/review/suggestions/'+encodeURIComponent(id)+'/reject?report_id='+encodeURIComponent(reportId||''), {reason: reason.trim()});
      global.toast('已驳回'); loadReviewPage();
    }catch(e){ global.toast(e.message); }
  };

  global.adoptSuggestion = async function(id, reportId){
    if(!isReviewBizDecider()){ global.toast('复盘决策仅业务超管可操作'); return; }
    const reports = global._reviewReportsCache || [];
    const rep = reports.find(r=>r.id===reportId) || reports[0];
    const sug = (rep&&rep.suggestions||[]).find(s=>s.id===id);
    const finding = (rep&&rep.findings||[]).find(f=>{
      const runs = new Set(sug&&sug.evidence_run_ids||[]);
      return (f.run_ids||[]).some(rid=>runs.has(rid));
    });
    try{
      await global.apiPost('/admin/review/suggestions/'+encodeURIComponent(id)+'/adopt', {
        suggestion_id: id,
        content_biz: (sug&&sug.content_biz)||('复盘建议 '+id),
        evidence_run_ids: sug&&sug.evidence_run_ids||[],
        report_id: reportId||null,
        finding_id: finding&&finding.id||null,
      });
      global.toast('已生成改进工单'); loadReviewPage();
    }catch(e){ global.toast(e.message); }
  };
  global.ticketAccept = async id=>{ try{ await global.apiPost('/admin/tickets/'+id+'/accept',{}); global.toast('已接单'); loadTicketsPage(true);}catch(e){global.toast(e.message);} };
  global.ticketComplete = async id=>{ try{ const r=await global.apiPost('/admin/tickets/'+id+'/complete',{}); global.toast(r.gate&&r.gate.passed?'门禁通过，请确认上线':'门禁未通过，已退回处理中'); loadTicketsPage(true);}catch(e){global.toast(e.message);} };
  global.ticketRelease = async id=>{ if(!confirm('确认测试门禁已通过并上线？'))return; try{ await global.apiPost('/admin/tickets/'+id+'/release',{}); global.toast('已上线'); loadTicketsPage(true);}catch(e){global.toast(e.message);} };
  // 移除发证/回收函数（新规格：薪资权岗位自带）

  // ── 员工花名册（Demo 种子数据，后续对接飞书组织架构）────────────
  const ORG_DIR = [
    { name:'张伟',  emp_id:'E10001' },
    { name:'李娜',  emp_id:'E10002' },
    { name:'王芳',  emp_id:'E10003' },
    { name:'刘洋',  emp_id:'E10004' },
    { name:'陈静',  emp_id:'E10005' },
    { name:'杨华',  emp_id:'E10006' },
    { name:'赵磊',  emp_id:'E10007' },
    { name:'黄敏',  emp_id:'E10008' },
    { name:'周鹏',  emp_id:'E10009' },
    { name:'吴霞',  emp_id:'E10010' },
    { name:'张明',  emp_id:'E10011' },
    { name:'张明',  emp_id:'E10012' }, // 重名演示
    { name:'刘婷',  emp_id:'E10013' },
    { name:'陈浩',  emp_id:'E10014' },
    { name:'林小燕',emp_id:'HR0002' },
    { name:'王建国', emp_id:'HR0003' },
    { name:'孙丽',  emp_id:'HR0004' },
    { name:'陈某',  emp_id:'E12099' },
    { name:'张HRD', emp_id:'HR0001' },
  ];

  // ── Autocomplete 辅助 ─────────────────────────────────────────
  // 用全局数组存候选项，onclick 直接传 index，避免 onblur 竞争问题
  global._acCandidates = { cuNameDrop: [], cuEmpDrop: [] };

  // 点击下拉项：全局函数（供 inline onclick 调用）
  global._acPick = function(dropId, idx){
    const p = (global._acCandidates[dropId] || [])[idx];
    if(!p) return;
    cuFillPerson(p);
  };

  function acShow(dropId, items){
    const drop = $(dropId);
    if(!drop) return;
    global._acCandidates[dropId] = items;
    if(!items.length){
      drop.innerHTML = `<div class="ac-empty">无匹配结果</div>`;
    } else {
      drop.innerHTML = items.map((p, i) =>
        `<div class="ac-item" data-idx="${i}"
          onmousedown="event.preventDefault()"
          onclick="_acPick('${dropId}',${i})">
          <span class="ac-item-name">${global.escAi(p.name)}</span>
          <span class="ac-item-emp">${global.escAi(p.emp_id)}</span>
        </div>`
      ).join('');
    }
    drop.classList.add('show');
  }

  function acHide(dropId){
    const drop = $(dropId);
    if(drop) drop.classList.remove('show');
  }

  function cuFillPerson(p){
    const nameEl = $('cuDisplayName');
    const empEl  = $('cuEmployeeId');
    if(nameEl) nameEl.value = p.name;
    if(empEl)  empEl.value  = p.emp_id;
    acHide('cuNameDrop');
    acHide('cuEmpDrop');
    cuValidatePair(); // 回填后立即清空错误
  }

  // 名字↔工号不匹配校验（仅当两者都在花名册中时比对）
  function cuValidatePair(){
    const name = ($('cuDisplayName').value||'').trim();
    const emp  = ($('cuEmployeeId').value||'').trim();
    const errEl = $('cuErrMsg');
    if(!name || !emp || !errEl) return;
    const nameInDir = ORG_DIR.some(p => p.name === name);
    const empInDir  = ORG_DIR.some(p => p.emp_id === emp);
    if(nameInDir || empInDir){
      // 至少一方在花名册，就要求对应关系存在
      const matched = ORG_DIR.some(p => p.name === name && p.emp_id === emp);
      if(!matched){
        errEl.textContent = `姓名「${name}」与工号「${emp}」不对应，请重新选择`;
        return;
      }
    }
    errEl.textContent = ''; // 通过或均为自定义值
  }

  function cuSearchName(){
    const q = ($('cuDisplayName').value || '').trim().toLowerCase();
    if(!q){ acHide('cuNameDrop'); return; }
    const matches = ORG_DIR.filter(p =>
      p.name.toLowerCase().includes(q) || p.emp_id.toLowerCase().includes(q)
    );
    acShow('cuNameDrop', matches);
  }

  function cuSearchEmpId(){
    const q = ($('cuEmployeeId').value || '').trim().toLowerCase();
    if(!q){ acHide('cuEmpDrop'); return; }
    const matches = ORG_DIR.filter(p =>
      p.emp_id.toLowerCase().includes(q) || p.name.toLowerCase().includes(q)
    );
    acShow('cuEmpDrop', matches);
  }

  // 绑定输入事件（modal 每次打开时绑定一次）
  function bindCuInputs(){
    const nameEl = $('cuDisplayName');
    const empEl  = $('cuEmployeeId');
    if(nameEl){
      nameEl.oninput = ()=>{ cuSearchName(); cuValidatePair(); };
      nameEl.onfocus = cuSearchName;
      nameEl.onblur  = ()=> setTimeout(()=> acHide('cuNameDrop'), 200);
    }
    if(empEl){
      empEl.oninput = ()=>{ cuSearchEmpId(); cuValidatePair(); };
      empEl.onfocus = cuSearchEmpId;
      empEl.onblur  = ()=> setTimeout(()=> acHide('cuEmpDrop'), 200);
    }
  }

  // ── 新建账号 ──────────────────────────────────────────────────
  global.openCreateUserModal = function(){
    // 清空表单
    ['cuDisplayName','cuEmployeeId','cuUsername','cuPassword'].forEach(id=>{
      const el = $(id); if(el) el.value = '';
    });
    const roleEl = $('cuRole'); if(roleEl) roleEl.value = 'staff';
    const errEl  = $('cuErrMsg'); if(errEl) errEl.textContent = '';
    acHide('cuNameDrop'); acHide('cuEmpDrop');
    openModal('createUserModal');
    setTimeout(()=>{ bindCuInputs(); $('cuDisplayName') && $('cuDisplayName').focus(); }, 50);
  };

  global.submitCreateUser = async function(){
    const errEl = $('cuErrMsg');
    const name  = ($('cuDisplayName').value||'').trim();
    const emp   = ($('cuEmployeeId').value||'').trim();
    const user  = ($('cuUsername').value||'').trim();
    const pass  = ($('cuPassword').value||'').trim();
    const role  = $('cuRole').value;
    if(!name||!emp||!user||!pass||!role){
      if(errEl) errEl.textContent = '所有带 * 的字段均为必填';
      return;
    }
    // 名字↔工号不匹配拦截
    const nameInDir = ORG_DIR.some(p => p.name === name);
    const empInDir  = ORG_DIR.some(p => p.emp_id === emp);
    if((nameInDir || empInDir) && !ORG_DIR.some(p => p.name === name && p.emp_id === emp)){
      if(errEl) errEl.textContent = `姓名「${name}」与工号「${emp}」不对应，请从下拉中选择`;
      return;
    }
    if(errEl) errEl.textContent = '';
    try{
      await global.apiPost('/admin/users',{username:user,password:pass,role,display_name:name,employee_id:emp});
      global.toast('创建成功');
      closeModal('createUserModal');
      loadUsersPage();
    }catch(e){
      if(errEl) errEl.textContent = e.message;
    }
  };

  // ── 编辑账号 ──────────────────────────────────────────────────
  let _euCurrentUsername = '';

  global.editUserPrompt = function(username, currentRole, currentName, currentActive){
    _euCurrentUsername = username;
    const unEl = $('euUsername'); if(unEl) unEl.textContent = username;
    const roleEl = $('euRole'); if(roleEl) roleEl.value = currentRole || 'staff';
    const nameEl = $('euDisplayName'); if(nameEl) nameEl.value = currentName || '';
    const actEl  = $('euIsActive');  if(actEl) actEl.value = (currentActive === false || currentActive === 0) ? '0' : '1';
    const errEl  = $('euErrMsg'); if(errEl) errEl.textContent = '';
    openModal('editUserModal');
    setTimeout(()=> $('euRole') && $('euRole').focus(), 50);
  };

  global.submitEditUser = async function(){
    const errEl  = $('euErrMsg');
    const role   = $('euRole').value || undefined;
    const name   = ($('euDisplayName').value||'').trim() || undefined;
    const active = $('euIsActive').value === '1';
    if(errEl) errEl.textContent = '';
    try{
      await global.apiPatch('/admin/users/'+encodeURIComponent(_euCurrentUsername),{role, display_name:name, is_active:active});
      global.toast('已更新');
      closeModal('editUserModal');
      loadUsersPage();
    }catch(e){
      if(errEl) errEl.textContent = e.message;
    }
  };

  global.apiPatch = async function(path, body){
    const res = await fetch(global.API_BASE + path, { method:'PATCH', headers:apiHeaders(), body:JSON.stringify(body||{}) });
    if(window.parseApiResponse) return window.parseApiResponse(res);
    const json = await res.json();
    if(!res.ok || json.code!==0) throw new Error(json.msg||('HTTP '+res.status));
    return json.data;
  };

  global._ticketNavReturn = null;

  global.openTicketFromReview = function(ticketId, reportId){
    global._ticketNavReturn = {
      page: 'review',
      reportId: reportId || '',
      week: ($('reviewWeekSelector') && $('reviewWeekSelector').value) || 'all',
    };
    if(isReviewBizDecider()){
      switchAdminPage('tickets');
    } else {
      switchAdminPage('my-tickets');
    }
    setTimeout(()=> showTicketDetail(ticketId, { fromReview: true }), 100);
  };

  global.returnFromTicketDetail = function(){
    const ret = global._ticketNavReturn;
    closeModal('ticketDetailModal');
    global._ticketNavReturn = null;
    if(!ret || ret.page !== 'review') return;
    switchAdminPage('review');
    const sel = $('reviewWeekSelector');
    if(sel && ret.week) sel.value = ret.week;
    loadReviewPageWithFilter();
  };

  // 从日期文本推导 ISO 周（如 "05-27复盘" → "2026-W22"，"2026-05-20~…" → "2026-W21"）
  function _guessISOWeek(text){
    if(!text) return null;
    let year, month, day;
    const full = text.match(/(\d{4})[/-](\d{1,2})[/-](\d{1,2})/);
    if(full){
      year  = parseInt(full[1]);
      month = parseInt(full[2]) - 1;
      day   = parseInt(full[3]);
    } else {
      const short = text.match(/(\d{1,2})[/-](\d{1,2})/);
      if(!short) return null;
      year  = new Date().getFullYear();
      month = parseInt(short[1]) - 1;
      day   = parseInt(short[2]);
    }
    const d = new Date(year, month, day);
    if(isNaN(d.getTime())) return null;
    // ISO 8601 week: 以包含当周周四的年份计算
    const thu = new Date(d);
    thu.setDate(d.getDate() + (4 - (d.getDay() || 7)));
    const yearStart = new Date(thu.getFullYear(), 0, 1);
    const weekNo = Math.ceil((((thu - yearStart) / 86400000) + 1) / 7);
    return `${thu.getFullYear()}-W${String(weekNo).padStart(2,'0')}`;
  }

  function _renderTicketDetailBody(t){
    const link  = t.source_link || {};
    const f     = link.finding || {};
    const isBiz = isReviewBizDecider();
    const dc    = (t.draft_changes && Object.keys(t.draft_changes).length) ? t.draft_changes : null;
    const rows  = [];

    // ── 状态行 ──────────────────────────────────────────
    rows.push(`<div class="td-row td-status-row">
      ${ticketStatusBadge(t.status)}
      <span class="td-meta">负责人：${global.escAi(assigneeLabel(t.assignee, t.assignee_label))}</span>
      <span class="td-meta">${global.escAi((t.updated_at||'').replace('T',' ').slice(0,16))}</span>
    </div>`);

    // ── 改进内容 ──────────────────────────────────────────
    if(isBiz){
      rows.push(`<div class="td-section">
        <div class="td-section-title">改进内容</div>
        <div class="td-content-biz">${global.escAi(t.content_biz || t.title || '—')}</div>
      </div>`);
    } else {
      const dcTarget = (dc && dc.target) || t.change_target;
      const dcAction = (dc && dc.action);
      const dcTest   = (dc && dc.add_test_case) || t.test_requirement;
      const draftRows = [
        dcTarget && `<div class="td-draft-row"><span class="td-draft-label">改动</span><span>${global.escAi(dcTarget)}</span></div>`,
        dcAction && `<div class="td-draft-row"><span class="td-draft-label">方案</span><span>${global.escAi(dcAction)}</span></div>`,
        dcTest   && `<div class="td-draft-row"><span class="td-draft-label">测试</span><span>${global.escAi(dcTest)}</span></div>`,
      ].filter(Boolean);
      rows.push(`<div class="td-section">
        <div class="td-section-title">改进内容</div>
        ${draftRows.length ? draftRows.join('') : `<span class="muted">${global.escAi(t.display_body || t.title || '—')}</span>`}
      </div>`);
    }

    // ── 来源 ──────────────────────────────────────────────
    const reportLabel = link.report_label || link.report_period || t.source || '';
    // 1) report_week 优先
    // 2) 兜底从 report_id 推导（"r-2026-w21" → "2026-W21"）
    // 3) 再兜底从 source 文本里解析日期推导 ISO 周
    let reportWeek = link.report_week || '';
    if(!reportWeek && link.report_id){
      const m = String(link.report_id).match(/(\d{4})-w(\d+)/i);
      if(m) reportWeek = `${m[1]}-W${String(m[2]).padStart(2,'0')}`;
    }
    if(!reportWeek && t.source){
      reportWeek = _guessISOWeek(t.source) || '';
    }
    const reportLink = reportLabel
      ? (reportWeek
          ? `<span class="action-link" onclick="jumpToReportWeek('${global.escAi(reportWeek)}',${t.id});closeModal('ticketDetailModal')">${global.escAi(reportLabel)} →</span>`
          : `<span>${global.escAi(reportLabel)}</span>`)
      : global.escAi(t.source || '—');
    rows.push(`<div class="td-section">
      <div class="td-section-title">来源</div>
      <div class="td-draft-row"><span class="td-draft-label">复盘</span><span>${reportLink}</span></div>
    </div>`);

    // ── 关联问题 ──────────────────────────────────────────
    if(f.id){
      if(isBiz){
        rows.push(`<div class="td-section">
          <div class="td-section-title">关联问题</div>
          <div class="td-biz-problem">${global.escAi(f.biz_problem || '—')}</div>
          ${f.impact ? `<div class="td-impact muted">${global.escAi(f.impact)}</div>` : ''}
        </div>`);
      } else {
        const runIds = (f.run_ids || []).join('、') || '—';
        rows.push(`<div class="td-section">
          <div class="td-section-title">关联问题（技术线索）</div>
          ${f.phenomenon  ? `<div class="td-draft-row"><span class="td-draft-label">现象</span><span>${global.escAi(f.phenomenon)}</span></div>` : ''}
          ${f.root_cause_hypothesis ? `<div class="td-draft-row"><span class="td-draft-label">归因</span><span class="td-hypothesis">${global.escAi(f.root_cause_hypothesis)}</span></div>` : ''}
          <div class="td-draft-row"><span class="td-draft-label">影响</span><span>${global.escAi(f.impact||'—')}</span></div>
          <div class="td-draft-row"><span class="td-draft-label">run_id</span><span class="td-runids">${global.escAi(runIds)}</span></div>
        </div>`);
      }
    }

    // ── 运行依据（技术侧额外展示） ────────────────────────
    if(!isBiz && t.evidence_run_ids && t.evidence_run_ids.length){
      rows.push(`<div class="td-section">
        <div class="td-section-title">运行依据</div>
        <div class="td-runids">${t.evidence_run_ids.map(r=>global.escAi(r)).join(' &nbsp;·&nbsp; ')}</div>
      </div>`);
    }

    // ── 驳回 / 门禁 ────────────────────────────────────────
    if(t.status === 'rejected' && t.reject_reason){
      rows.push(`<div class="tk-reject-reason"><span class="tk-reject-label">驳回理由</span>${global.escAi(t.reject_reason)}</div>`);
    }
    if(t.gate_result){
      rows.push(`<div class="td-section">
        <div class="td-section-title">门禁结果</div>
        <div class="muted" style="font-size:12px;font-family:monospace;word-break:break-all">${global.escAi(t.gate_result)}</div>
      </div>`);
    }

    // ── 备注 ────────────────────────────────────────────────
    const notes = (t.notes||[]).map(n =>
      `<div class="ticket-note-item">
        <span class="muted">${global.escAi((n.created_at||'').replace('T',' ').slice(0,16))} · ${global.escAi(n.author||n.author_label||'')}</span>
        <div>${global.escAi(n.content||'')}</div>
      </div>`
    ).join('');
    rows.push(`<div class="ticket-notes-block">
      <strong>备注</strong>
      ${notes || '<p class="muted" style="margin:6px 0">暂无备注</p>'}
    </div>`);

    return rows.join('');
  }

  global._reviewNavReturn  = null;
  global._pendingReviewWeek = null;

  global.jumpToReportWeek = function(week, ticketId){
    const fromPage = isReviewBizDecider() ? 'tickets' : 'my-tickets';
    global._reviewNavReturn   = { page: fromPage, ticketId: ticketId || null };
    global._pendingReviewWeek = week || null;
    // 先激活复盘 pane（不走 switchAdminPage 以避免其自动清空 _reviewNavReturn）
    document.querySelectorAll('.admin-pane').forEach(p => p.classList.remove('active'));
    const pane = $('admin-review');
    if(pane) pane.classList.add('active');
    syncAuthRoleFromStorage && syncAuthRoleFromStorage();
    // 加载复盘（内部会用 _pendingReviewWeek 预选周期）
    loadReviewPage();
    // 显示返回浮条
    const floatEl = $('backFloatTickets');
    const txtEl   = $('bfTicketsTxt');
    if(txtEl) txtEl.innerHTML = `已跳转至 <b>${global.escAi(week||'')}</b> 复盘报告`;
    if(floatEl) floatEl.classList.add('show');
  };

  global.hideBackFloatTickets = function(){
    const floatEl = $('backFloatTickets');
    if(floatEl) floatEl.classList.remove('show');
  };

  global.returnFromReviewToTickets = function(){
    const ret = global._reviewNavReturn;
    global._reviewNavReturn   = null;
    global._pendingReviewWeek = null;
    global.hideBackFloatTickets();
    if(!ret) return;
    switchAdminPage(ret.page);
    if(ret.ticketId){
      setTimeout(()=> showTicketDetail(ret.ticketId), 80);
    }
  };

  global.showTicketDetail = async function(id, opts){
    opts = opts || {};
    try{
      const t = await global.apiGet('/admin/tickets/'+id);
      const titleEl = $('ticketDetailTitle');
      const bodyEl  = $('ticketDetailBody');
      const footEl  = $('ticketDetailFooter');
      const backEl  = $('ticketBackReview');
      if(!bodyEl){ global.toast('详情弹层未加载'); return; }

      // 标题：工单号可点击跳转复盘（若有来源报告周期）
      const link = t.source_link || {};
      let rWeek = link.report_week || '';
      if(!rWeek && link.report_id){
        const m = String(link.report_id).match(/(\d{4})-w(\d+)/i);
        if(m) rWeek = `${m[1]}-W${String(m[2]).padStart(2,'0')}`;
      }
      if(!rWeek && t.source) rWeek = _guessISOWeek(t.source) || '';
      if(titleEl){
        if(rWeek){
          titleEl.innerHTML = `工单 <span class="action-link" title="跳转至来源复盘报告" onclick="jumpToReportWeek('${global.escAi(rWeek)}',${t.id});closeModal('ticketDetailModal')">${global.escAi(t.ticket_no)}</span>`;
        } else {
          titleEl.textContent = `工单 ${t.ticket_no}`;
        }
      }

      if(backEl){
        backEl.style.display = (opts.fromReview || global._ticketNavReturn) ? 'inline' : 'none';
      }

      bodyEl.innerHTML = _renderTicketDetailBody(t);

      if(footEl){
        let foot = `<button class="btn" onclick="closeModal('ticketDetailModal')">关闭</button>`;
        if(t.status !== 'rejected' && isReviewBizDecider()){
          foot += ` <button class="btn btn-primary" onclick="openTicketNoteEditor(${id})">编辑备注</button>`;
        }
        footEl.innerHTML = foot;
      }
      openModal('ticketDetailModal');
    }catch(e){ global.toast(e.message); }
  };

  let _ticketNoteEditingId = null;

  global.openTicketNoteEditor = async function(id){
    _ticketNoteEditingId = id;
    const histHost = $('ticketNoteHistory');
    const input = $('ticketNoteInput');
    const noEl = $('ticketNoteModalNo');
    if(input) input.value = '';
    if(histHost) histHost.innerHTML = '<div class="muted" style="font-size:12px">加载中…</div>';
    openModal('ticketNoteModal');
    try{
      const t = await global.apiGet('/admin/tickets/'+id);
      if(noEl) noEl.textContent = t.ticket_no || ('#'+id);
      if(histHost){
        const notes = t.notes || [];
        histHost.innerHTML = notes.length
          ? notes.map(n=>`<div class="ticket-note-item"><span class="muted">${global.escAi((n.created_at||'').replace('T',' ').slice(0,16))} · ${global.escAi(n.author||n.author_label||'')}</span><div>${global.escAi(n.content||'')}</div></div>`).join('')
          : '<div class="muted" style="font-size:12px">暂无历史备注</div>';
      }
    }catch(e){
      if(histHost) histHost.innerHTML = `<div class="rv-empty-error" style="font-size:12px">${global.escAi(e.message)}</div>`;
    }
  };

  global.submitTicketNote = async function(){
    const id = _ticketNoteEditingId;
    const input = $('ticketNoteInput');
    if(!id || !input) return;
    const text = (input.value || '').trim();
    if(!text){
      global.toast('请填写备注内容', 'danger');
      return;
    }
    try{
      await global.apiPost('/admin/tickets/'+id+'/notes', { content: text });
      global.toast('备注已保存');
      closeModal('ticketNoteModal');
      _ticketNoteEditingId = null;
      loadTicketsPage(false);
      loadTicketsPage(true);
    }catch(e){ global.toast(e.message); }
  };

  global.ticketReject = async function(id){
    if(!canOperateTickets()){ global.toast('仅技术超管可驳回工单'); return; }
    const reason = prompt('驳回理由（必填）');
    if(!reason || !reason.trim()) return;
    try{
      await global.apiPost('/admin/tickets/'+id+'/reject', { reason: reason.trim() });
      global.toast('已驳回');
      loadTicketsPage(true);
    }catch(e){ global.toast(e.message); }
  };

  global.withdrawTicket = async function(id){
    if(!confirm('确认撤回此工单？仅待处理且未接单时可撤回。')) return;
    try{
      await global.apiPost('/admin/tickets/'+id+'/withdraw', {});
      global.toast('已撤回');
      loadTicketsPage(false);
    }catch(e){ global.toast(e.message); }
  };

  let _evalPollTimer = null;
  let _evalSelectedRunId = null;

  function evalStatusLabel(st){
    if(st==='running') return '<span class="ev-status-running">运行中</span>';
    if(st==='done') return '<span class="ev-status-done">已完成</span>';
    if(st==='failed') return '<span class="ev-status-failed">失败</span>';
    return global.escAi(st||'—');
  }

  function pct(n){ return n==null?'—':(n*100).toFixed(1)+'%'; }
  function scoreFmt(n){ return n==null?'—':Number(n).toFixed(2); }

  async function loadEvalPage(){
    const listHost = $('evalRunList');
    const detailHost = $('evalRunDetail');
    if(!listHost) return;
    const triggerL1 = $('evalTriggerL1');
    const triggerFull = $('evalTriggerFull');
    if(triggerL1) triggerL1.style.display = canOperateTickets()?'':'none';
    if(triggerFull) triggerFull.style.display = canOperateTickets()?'':'none';
    listHost.innerHTML = '<div class="rv-empty">加载中…</div>';
    try{
      const data = await global.apiGet('/admin/eval/runs?limit=20');
      const items = data.items||[];
      if(!items.length){
        listHost.innerHTML = '<div class="rv-empty">暂无跑批记录</div>';
        if(detailHost) detailHost.innerHTML = '<div class="rv-empty">技术超管可点击上方按钮触发评测</div>';
        return;
      }
      listHost.innerHTML = items.map(r=>{
        const active = r.id===_evalSelectedRunId?' active':'';
        const l1 = r.layer1||{};
        const acc = l1.accuracy!=null?pct(l1.accuracy):'—';
        return `<div class="ev-run-item${active}" onclick="selectEvalRun(${r.id})">
          <div><strong>#${r.id}</strong> ${global.escAi(r.version||'')} · ${evalStatusLabel(r.status)}</div>
          <div class="ev-run-meta">L1 ${acc} · ${global.escAi((r.started_at||'').replace('T',' ').slice(0,16))}</div>
        </div>`;
      }).join('');
      const running = items.find(r=>r.status==='running');
      if(running){
        _evalSelectedRunId = running.id;
        startEvalPoll(running.id);
      } else if(!_evalSelectedRunId && items[0]){
        selectEvalRun(items[0].id);
      } else if(_evalSelectedRunId){
        selectEvalRun(_evalSelectedRunId);
      }
    }catch(e){
      listHost.innerHTML = `<div class="rv-empty rv-empty-error">${global.escAi(e.message)}</div>`;
    }
  }
  global.loadEvalPage = loadEvalPage;

  function startEvalPoll(runId){
    if(_evalPollTimer) clearInterval(_evalPollTimer);
    const statusEl = $('evalTriggerStatus');
    if(statusEl) statusEl.textContent = '跑批进行中…';
    _evalPollTimer = setInterval(async ()=>{
      try{
        const d = await global.apiGet('/admin/eval/runs/'+runId, {include_cases:false});
        if(d.status!=='running'){
          clearInterval(_evalPollTimer);
          _evalPollTimer = null;
          if(statusEl) statusEl.textContent = '';
          loadEvalPage();
        }
      }catch(_e){ /* ignore poll errors */ }
    }, 4000);
  }

  global.selectEvalRun = async function(runId){
    _evalSelectedRunId = runId;
    const detailHost = $('evalRunDetail');
    if(!detailHost) return;
    detailHost.innerHTML = '<div class="rv-empty">加载报告…</div>';
    document.querySelectorAll('.ev-run-item').forEach(el=>{
      el.classList.toggle('active', el.getAttribute('onclick')===`selectEvalRun(${runId})`);
    });
    try{
      const r = await global.apiGet('/admin/eval/runs/'+runId);
      detailHost.innerHTML = renderEvalReport(r);
    }catch(e){
      detailHost.innerHTML = `<div class="rv-empty rv-empty-error">${global.escAi(e.message)}</div>`;
    }
  };

  function renderEvalReport(r){
    const l1=r.layer1||{}, l2=r.layer2||{}, l3=r.layer3||{};
    const cmp = r.compare_prev||{};
    const delta = cmp.delta_total_score;
    const deltaTxt = delta==null?'':(delta>=0?` ↑${delta.toFixed(2)}`:` ↓${Math.abs(delta).toFixed(2)}`);
    const metrics = `
      <div class="rv-metrics">
        ${renderReviewMetric('总分', scoreFmt(r.total_score)+deltaTxt)}
        ${renderReviewMetric('L1 意图准确率', pct(l1.accuracy))}
        ${renderReviewMetric('L2 检索命中', pct(l2.hit_rate))}
        ${renderReviewMetric('L3 答案均分', scoreFmt(l3.avg))}
      </div>`;
    const rubric = l3.scored ? `
      <div class="rv-section">
        <div class="rv-section-title">L3 分项均分（1-5）</div>
        <div class="rv-metrics">
          ${renderReviewMetric('正确性', scoreFmt(l3.correctness_avg))}
          ${renderReviewMetric('完整性', scoreFmt(l3.completeness_avg))}
          ${renderReviewMetric('引用', scoreFmt(l3.citation_avg))}
          ${renderReviewMetric('合规', scoreFmt(l3.compliance_avg))}
        </div>
      </div>` : '';
    const intents = r.intent_breakdown||{};
    const intentHtml = Object.keys(intents).length ? `
      <div class="rv-section">
        <div class="rv-section-title">按意图分布（L3 均分）</div>
        <div class="ev-intent-grid">
          ${Object.entries(intents).map(([k,v])=>`
            <div class="ev-intent-cell">
              <div class="ev-intent-name">${global.escAi(k)}</div>
              <div class="ev-intent-score">${scoreFmt(v.avg)}</div>
              <div class="ev-run-meta">n=${v.count||0}</div>
            </div>`).join('')}
        </div>
      </div>` : '';
    const weak = (r.weakness_summary||[]).map(w=>`
      <div class="ev-weak">${global.escAi(w.hint||w.kind||'')}</div>`).join('');
    const weakHtml = weak ? `<div class="rv-section"><div class="rv-section-title">弱项清单</div>${weak}</div>` : '';
    const fails = (r.case_results||[]).filter(c=>!c.passed).slice(0,12);
    const failHtml = fails.length ? `
      <div class="rv-section">
        <div class="rv-section-title">未通过样本（最多展示 12 条）</div>
        ${fails.map(c=>`<div class="rv-finding">
          <div class="rv-finding-text">${global.escAi(c.case_id)} · Layer ${c.layer}</div>
          <div class="ev-case-fail">${global.escAi(c.error||(c.score_detail&&JSON.stringify(c.score_detail))||'')}</div>
        </div>`).join('')}
      </div>` : '';
    const head = `
      <div class="rv-report">
        <div class="rv-report-head">
          <div class="rv-report-title">Eval #${r.id} · ${global.escAi(r.version||'')}</div>
          <div class="rv-report-meta">${evalStatusLabel(r.status)} · ${global.escAi((r.started_at||'').replace('T',' ').slice(0,16))} · ${r.duration_ms||'—'}ms · ${r.total_cases||0} 条</div>
        </div>`;
    return head + metrics + rubric + intentHtml + weakHtml + failHtml + '</div>';
  }

  global.triggerEvalRun = async function(onlyLayer1){
    if(!canOperateTickets()){ global.toast('仅技术超管可触发评测'); return; }
    const ver = prompt('版本标签（可选）','eval-'+new Date().toISOString().slice(0,10)) || 'dev';
    const statusEl = $('evalTriggerStatus');
    if(statusEl) statusEl.textContent = '正在启动…';
    try{
      const q = 'only_layer1='+(onlyLayer1?'true':'false')+'&version='+encodeURIComponent(ver);
      const data = await global.apiPost('/admin/eval/runs?'+q, {});
      global.toast(data.message||'已启动');
      _evalSelectedRunId = data.run_id;
      if(data.run_id) startEvalPoll(data.run_id);
      loadEvalPage();
    }catch(e){
      if(statusEl) statusEl.textContent = '';
      global.toast(e.message);
    }
  };
  
  global.isPayrollL3 = isPayrollL3;
})(window);
