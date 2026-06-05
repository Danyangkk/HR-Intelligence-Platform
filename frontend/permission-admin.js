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
    const adminMain = document.querySelector('#pane-admin .admin-content');
    if(adminMain) adminMain.classList.toggle('admin-eval-mode', page === 'eval');
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
  let _evalCases = [];
  let _evalDiff = null;
  let _evalCurrentRun = null;
  let _evalCaseFilter = 'all';

  function evalStatusLabel(st){
    if(st==='running') return '<span class="ev-status-running">运行中</span>';
    if(st==='done') return '<span class="ev-status-done">已完成</span>';
    if(st==='failed') return '<span class="ev-status-failed">失败</span>';
    return global.escAi(st||'—');
  }

  function evalStatusBadge(st){
    if(st==='running') return '<span class="ev-run-status running">运行中</span>';
    if(st==='done') return '<span class="ev-run-status done">已完成</span>';
    if(st==='failed') return '<span class="ev-run-status failed">失败</span>';
    return `<span class="ev-run-status">${global.escAi(st||'—')}</span>`;
  }

  function pct(n){ return n==null?'—':(n*100).toFixed(1)+'%'; }
  function scoreFmt(n){ return n==null?'—':Number(n).toFixed(2); }

  function renderEvalMetric(label, value, sub, warn){
    const cls = warn ? ' rv-metric-warn' : '';
    return `<div class="rv-metric${cls}"><div class="rv-metric-label">${label}</div><div class="rv-metric-value">${value}</div>${sub?`<div class="ev-metric-sub">${sub}</div>`:''}</div>`;
  }

  function evalLayerMark(row, layerNum){
    if(_evalRunProfile === 'layer1_only' && layerNum > 1){
      return '<span class="ev-mark-na" style="font-size:11px">该层未运行</span>';
    }
    if(!row) return '<span class="ev-mark-na">—</span>';
    return row.passed ? '<span class="ev-mark-ok">✓</span>' : '<span class="ev-mark-err">✗</span>';
  }

  function evalL3Score(row){
    if(_evalRunProfile === 'layer1_only'){
      return '<span class="ev-mark-na" style="font-size:11px">该层未运行</span>';
    }
    if(!row) return '<span class="ev-mark-na">—</span>';
    if(row.error && !row.scored) return '<span class="ev-mark-err" title="'+global.escAi(row.error)+'">!</span>';
    if(row.score==null) return '<span class="ev-mark-na">—</span>';
    const cls = row.score < 4 ? 'ev-score-warn' : 'ev-score-ok';
    return `<span class="${cls}">${Number(row.score).toFixed(1)}</span>`;
  }

  // PR6: L1/L2/L3；PR7.6 落地后改为 plan/reslv/retrv/analy/critic/answer 即可
  const EVAL_TABLE_LAYERS = [
    { layer: 1, header: 'L1', cell: g => evalLayerMark(g.layers[1], 1) },
    { layer: 2, header: 'L2', cell: g => evalLayerMark(g.layers[2], 2) },
    { layer: 3, header: 'L3 分', cell: g => evalL3Score(g.layers[3]) },
  ];

  function evalRunGateDot(r){
    const st = r.gate_status || 'no_data';
    if(st === 'no_data'){
      return '<span class="ev-gate-dot na" title="无数据"></span>';
    }
    if(r.gate_passed){
      return '<span class="ev-gate-dot pass" title="门禁通过"></span>';
    }
    return '<span class="ev-gate-dot fail" title="门禁未过"></span>';
  }

  function evalDefaultVersion(){
    const d = new Date();
    const pad = n => String(n).padStart(2,'0');
    return pad(d.getMonth()+1)+pad(d.getDate())+'-'+pad(d.getHours())+pad(d.getMinutes());
  }

  function bindEvalCaseTableClicks(){
    const host = $('evalCaseTableHost');
    if(!host || host._evalClickBound) return;
    host._evalClickBound = true;
    host.addEventListener('click', ev=>{
      const tr = ev.target.closest('tr.ev-case-row');
      if(!tr) return;
      const caseId = tr.getAttribute('data-case-id');
      if(caseId) global.openEvalCaseModal(caseId);
    });
  }

  function evalTruncate(s, n){
    const t = String(s||'');
    return t.length > n ? t.slice(0, n)+'…' : t;
  }

  function groupEvalCaseRows(items){
    const map = {};
    (items||[]).forEach(row=>{
      if(!map[row.case_id]){
        map[row.case_id] = {
          case_id: row.case_id,
          query: row.query,
          intent: row.intent,
          declared_layers: row.declared_layers || [1],
          layers: {},
        };
      }
      if(row.declared_layers){
        map[row.case_id].declared_layers = row.declared_layers;
      }
      map[row.case_id].layers[row.layer] = row;
    });
    return map;
  }

  function evalCaseFailed(group){
    return EVAL_TABLE_LAYERS.some(c=>group.layers[c.layer] && !group.layers[c.layer].passed);
  }

  function evalCaseSortKey(group){
    const failed = evalCaseFailed(group) ? 0 : 1;
    const l3 = group.layers[3];
    const score = (l3 && l3.score!=null) ? l3.score : 99;
    return [failed, score, group.case_id];
  }

  function renderEvalCaseTable(items, diff){
    const grouped = Object.values(groupEvalCaseRows(items));
    grouped.sort((a,b)=>{
      const ka = evalCaseSortKey(a), kb = evalCaseSortKey(b);
      for(let i=0;i<ka.length;i++){
        if(ka[i]<kb[i]) return -1;
        if(ka[i]>kb[i]) return 1;
      }
      return 0;
    });
    const regSet = new Set((diff&&diff.regressed)||[]);
    const fixSet = new Set((diff&&diff.fixed)||[]);
    let rows = grouped;
    if(_evalCaseFilter==='regressed') rows = grouped.filter(g=>regSet.has(g.case_id));
    else if(_evalCaseFilter==='fixed') rows = grouped.filter(g=>fixSet.has(g.case_id));

    if(!rows.length){
      return '<div class="rv-empty">暂无匹配的用例</div>';
    }
    return `<div class="table-wrap"><table class="sheet-table ev-case-table"><thead><tr>
      <th>case</th><th>query</th><th>意图</th>${EVAL_TABLE_LAYERS.map(c=>`<th>${c.header}</th>`).join('')}<th>flaky</th>
    </tr></thead><tbody>${rows.map(g=>{
      const tag = regSet.has(g.case_id)?'<span class="ev-regressed-tag">新挂</span>':'';
      return `<tr class="ev-case-row" data-case-id="${global.escAi(g.case_id)}">
        <td>${tag}${global.escAi(g.case_id)}</td>
        <td title="${global.escAi(g.query||'')}">${global.escAi(evalTruncate(g.query,30))}</td>
        <td>${global.escAi(g.intent||'—')}</td>
        ${EVAL_TABLE_LAYERS.map(c=>`<td>${c.cell(g)}</td>`).join('')}
        <td>${g.layers[1]&&g.layers[1].flaky?'<span class="ev-flaky-tag">flaky</span>':''}</td>
      </tr>`;
    }).join('')}</tbody></table></div>`;
  }

  let _evalMetrics = null;
  let _evalRunProfile = 'full';

  function evalLayerPlaceholder(layerNum, row, declaredLayers){
    const declared = declaredLayers || [];
    if(!declared.includes(layerNum)){
      return '— 未声明断言';
    }
    if(_evalRunProfile === 'layer1_only' && layerNum > 1){
      return '该层未运行（本次为仅意图层跑批）';
    }
    if(!row || (!row.expected && !row.actual)){
      return '该次运行未保存断言快照';
    }
    return null;
  }

    function judgeOverallInt(score){
    if(score == null || score === '') return null;
    return Math.max(1, Math.min(5, Math.round(Number(score))));
  }

  function renderEvalReport(r, diff, metrics){
    metrics = metrics || {};
    const layer1Only = _evalRunProfile === 'layer1_only' || metrics.eval_profile === 'layer1_only';
    const assertion = metrics.assertion || {};
    const cal = metrics.judge_calibration || {};
    const deltaL3 = metrics.delta_grader_avg;
    const deltaTxt = (!layer1Only && deltaL3!=null) ? (deltaL3>=0?` ↑${deltaL3.toFixed(2)}`:` ↓${Math.abs(deltaL3).toFixed(2)}`) : '';
    let gateBadge;
    if(metrics.gate_status === 'no_data'){
      gateBadge = '<span class="ev-gate ev-gate-na">无数据</span>';
    } else if(metrics.gate_passed){
      gateBadge = '<span class="ev-gate ev-gate-pass">门禁通过</span>';
    } else {
      gateBadge = '<span class="ev-gate ev-gate-fail">门禁未过</span>';
    }
    const l1pct = metrics.planner_accuracy!=null ? (metrics.planner_accuracy*100).toFixed(1)+'%' : '';
    const plannerBadge = l1pct ? `<span class="muted">planner ${l1pct}</span>` : '';
    const weakest = metrics.weakest_link || '无失败';
    const calN = cal.sample_count || 0;
    let calVal;
    let calWarnFlag = false;
    if(layer1Only){
      calVal = '该层未运行';
    } else if(calN >= 20 && cal.agreement_rate != null){
      calVal = Number(cal.agreement_rate).toFixed(2);
      calWarnFlag = !!cal.warn;
    } else {
      calVal = `样本不足（${calN}/20）`;
    }
    const calWarn = (!layer1Only && calWarnFlag) ? '<div class="ev-cal-banner">judge 分数仅供参考，需重新校准 rubric（与人工一致率 &lt; 0.8）</div>' : '';
    const flakyN = metrics.flaky_count || 0;
    const metaDur = r.duration_ms != null ? `${r.duration_ms}ms · ` : '';
    const graderScore = layer1Only ? '该层未运行' : (metrics.grader_avg!=null ? Number(metrics.grader_avg).toFixed(2) : '—');
    const metricsHtml = `
      <div class="rv-metrics">
        ${renderEvalMetric('assertion', `${assertion.passed??'—'}/${assertion.total??'—'}`, '代码断言通过 / 总数')}
        ${renderEvalMetric('grader 均分', graderScore+deltaTxt, '模型裁判 overall 平均（1-5）')}
        ${renderEvalMetric('grader 校准', calVal, '与人工评分一致率（&lt;0.8 预警）', calWarnFlag)}
        ${renderEvalMetric('最弱环节', global.escAi(weakest), '失败聚类最大簇')}
      </div>`;
    const head = `
      <div class="rv-report">
        <div class="rv-report-head">
          <div>
            <div class="rv-report-title">Run #${r.id} 报告 · ${global.escAi(r.version||'')} ${gateBadge} ${plannerBadge}<span class="ev-flaky-tag">flaky ${flakyN} 例</span></div>
            <div class="rv-report-meta">${evalStatusLabel(r.status)} · ${global.escAi((r.started_at||'').replace('T',' ').slice(0,16))} · ${metaDur}${r.total_cases||0} 条</div>
          </div>
          <div class="ev-report-actions">
            <button class="btn btn-sm" onclick="openEvalCoverageModal()">覆盖矩阵</button>
          </div>
        </div>
        ${calWarn}${metricsHtml}
        <div class="ev-case-toolbar">
          <div class="rv-section-title" style="margin:0;border:0;padding:0">用例明细（失败优先）· 点行打开详情</div>
          <div class="ev-case-filters">
            <button class="btn btn-sm${_evalCaseFilter==='all'?' active':''}" onclick="setEvalCaseFilter('all')">全部</button>
            <button class="btn btn-sm${_evalCaseFilter==='regressed'?' active':''}" onclick="setEvalCaseFilter('regressed')">新挂</button>
            <button class="btn btn-sm${_evalCaseFilter==='fixed'?' active':''}" onclick="setEvalCaseFilter('fixed')">修复</button>
          </div>
        </div>
        <div id="evalCaseTableHost">${renderEvalCaseTable(_evalCases, diff)}</div>
      </div>`;
    return head;
  }

  global.setEvalCaseFilter = function(filter){
    _evalCaseFilter = filter;
    const host = $('evalCaseTableHost');
    if(host && _evalCurrentRun) host.innerHTML = renderEvalCaseTable(_evalCases, _evalDiff);
    bindEvalCaseTableClicks();
  };

  function evalPassBadge(passed){
    return passed ? '<span class="ev-mark-ok">✓ pass</span>' : '<span class="ev-mark-err">✗ fail</span>';
  }

  function renderEvalLayer1Block(row, declaredLayers){
    const ph = evalLayerPlaceholder(1, row, declaredLayers);
    if(ph){
      return `<div class="ev-layer-block"><div class="ev-layer-head"><div class="ev-layer-title">Layer 1 意图与计划断言</div></div><div class="muted">${ph}</div></div>`;
    }
    const exp = row.expected||{};
    const act = row.actual||{};
    const mism = (row.score_detail&&row.score_detail.mismatches)||[];
    const left = `<div class="ev-dual-col"><h4>期望 expected</h4>
      <div>intent: ${global.escAi(exp.intent||'—')}</div>
      ${exp.plan_constraints?`<div>plan_constraints: ${global.escAi(JSON.stringify(exp.plan_constraints))}</div>`:''}
    </div>`;
    const right = `<div class="ev-dual-col"><h4>实际 actual</h4>
      <div>intent: ${global.escAi(act.intent||'—')} ${exp.intent&&act.intent===exp.intent?'✓':'✗'}</div>
      <div>rejected: ${global.escAi(String(!!act.rejected))}</div>
      <div>clarify: ${global.escAi(String(!!act.clarify))}</div>
      ${mism.length?`<pre class="ev-mismatch">${mism.map(m=>global.escAi(m)).join('\n')}</pre>`:''}
    </div>`;
    return `<div class="ev-layer-block"><div class="ev-layer-head"><div class="ev-layer-title">Layer 1 意图与计划断言</div>${evalPassBadge(row.passed)}</div><div class="ev-dual">${left}${right}</div></div>`;
  }

  function renderEvalLayer2Block(row, declaredLayers){
    const ph = evalLayerPlaceholder(2, row, declaredLayers);
    if(ph){
      return `<div class="ev-layer-block"><div class="ev-layer-head"><div class="ev-layer-title">Layer 2 检索命中断言</div></div><div class="muted">${ph}</div></div>`;
    }
    const exp = row.expected||{};
    const act = row.actual||{};
    const missMod = (row.score_detail&&row.score_detail.missing_modules)||[];
    const missDoc = (row.score_detail&&row.score_detail.missing_doc_chunks)||[];
    const expMods = exp.expected_modules||[];
    const expDocs = exp.expected_doc_chunks||[];
    const actMods = act.modules||[];
    const actDocs = act.doc_chunks||[];
    const modLines = expMods.map(m=>{
      const hit = actMods.some(am=>String(am).includes(m));
      return `<div>${global.escAi(m)} ${hit?'<span class="ev-mark-ok">✓</span>':'<span class="ev-mark-err">0 行 ✗ 未命中</span>'}</div>`;
    }).join('') || '<div class="muted">无模块期望</div>';
    const docLines = expDocs.map(d=>{
      const hit = actDocs.some(ad=>String(ad).includes(d)||String(d).includes(ad));
      return `<div>${global.escAi(d)} ${hit?'<span class="ev-mark-ok">✓</span>':'<span class="ev-mark-err">0 段 ✗ 未命中</span>'}</div>`;
    }).join('') || '<div class="muted">无文档块期望</div>';
    let rightContent = `<div>模块: ${global.escAi(actMods.join('、')||'—')}</div><div>文档: ${global.escAi(actDocs.join('、')||'—')}</div>`;
    if(missMod.length||missDoc.length){
      rightContent += `<div class="ev-mismatch">${[...missMod,...missDoc].map(m=>global.escAi(m)).join('\n')}</div>`;
    }
    return `<div class="ev-layer-block"><div class="ev-layer-head"><div class="ev-layer-title">Layer 2 检索命中断言</div>${evalPassBadge(row.passed)}</div><div class="ev-dual">
      <div class="ev-dual-col"><h4>期望命中</h4>${modLines}${docLines}</div>
      <div class="ev-dual-col"><h4>实际证据</h4>${rightContent}</div>
    </div></div>`;
  }

  function judgeBadgeClass(v){
    if(v==null) return 'ev-judge-badge';
    if(v <= 2) return 'ev-judge-badge err';
    if(v < 4) return 'ev-judge-badge warn';
    return 'ev-judge-badge ok';
  }

  function renderEvalLayer3Block(row, declaredLayers){
    const ph = evalLayerPlaceholder(3, row, declaredLayers);
    if(ph){
      return `<div class="ev-layer-block"><div class="ev-layer-head"><div class="ev-layer-title">Layer 3 judge</div></div><div class="muted">${ph}</div></div>`;
    }
    if(row.error && !row.scored){
      return `<div class="ev-layer-block"><div class="ev-layer-head"><div class="ev-layer-title">Layer 3 judge</div></div><div class="ev-mismatch">${global.escAi(row.error)}</div></div>`;
    }
    const exp = row.expected||{};
    const act = row.actual||{};
    const detail = row.score_detail||{};
    const points = (exp.answer_points||[]).map(p=>`<div>· ${global.escAi(p)}</div>`).join('')||'<div class="muted">—</div>';
    const forbid = (exp.forbid||[]).map(p=>`<div class="ev-mark-err">禁止: ${global.escAi(p)}</div>`).join('');
    const metrics = (exp.metric_callouts||[]).map(p=>`<div>口径: ${global.escAi(p)}</div>`).join('');
    const cites = (exp.expected_citations||[]).map(c=>`<div>${global.escAi(JSON.stringify(c))}</div>`).join('');
    const answer = act.answer || act.answer_preview || '';
    const actCites = (act.citations||[]).slice(0,8).map(c=>`<div>${global.escAi(JSON.stringify(c))}</div>`).join('')||'<div class="muted">—</div>';
    const badges = ['correctness','completeness','citation','compliance'].map(k=>
      `<span class="${judgeBadgeClass(detail[k])}">${k} ${detail[k]!=null?Number(detail[k]).toFixed(1):'—'}</span>`
    ).join('');
    const viol = (row.violations||[]).map(v=>`<div class="ev-mark-err">${global.escAi(typeof v==='string'?v:JSON.stringify(v))}</div>`).join('');
    const isDemoRun = _evalCurrentRun && _evalCurrentRun.trigger === 'demo';
    const canFeedback = row.scored && row.score != null && (!row.feedback || isDemoRun);
    const fb = row.feedback;
    const fbDone = fb ? `<div class="ev-feedback-done">已记录：${fb.verdict==='agree'?'同意':'不同意'} · 人工分 ${fb.human_overall??'—'}${fb.note?' · '+global.escAi(fb.note):''}</div>` : '';
    const fbDemoHint = isDemoRun && fb ? '<div class="muted" style="font-size:11px;margin-top:6px">demo 可改判，提交后更新 grader 校准卡</div>' : '';
    const fbForm = canFeedback ? `<div class="ev-feedback-bar" id="evalFeedbackBar"${fb?' style="margin-top:8px"':''}>
        <button type="button" class="btn btn-sm" id="evalFbAgree" onclick="selectEvalFeedbackVerdict('agree')">同意</button>
        <button type="button" class="btn btn-sm" id="evalFbDisagree" onclick="selectEvalFeedbackVerdict('disagree')">不同意</button>
        <label class="muted ev-fb-score-wrap" id="evalFbScoreWrap" style="flex-direction:row;align-items:center;gap:4px">人工分<input type="number" id="evalFbScore" min="1" max="5" step="1" placeholder="1-5"></label>
        <span class="ev-fb-score-hint muted" id="evalFbScoreHint"></span>
        <input type="text" id="evalFbNote" placeholder="备注（可选）">
        <button type="button" class="btn btn-sm btn-primary" onclick="submitEvalFeedback()">提交</button>
      </div>` : '';
    const fbBar = fbDone + fbDemoHint + fbForm;
    return `<div class="ev-layer-block"><div class="ev-layer-head"><div class="ev-layer-title">Layer 3 judge</div>${evalPassBadge(row.passed)}</div><div class="ev-dual">
      <div class="ev-dual-col"><h4>评判依据</h4>${points}${forbid}${metrics}${cites}</div>
      <div class="ev-dual-col"><h4>被评对象</h4><div class="ev-answer-box">${global.escAi(answer)}</div><h4 style="margin-top:10px">实际 citations</h4>${actCites}</div>
    </div>
    <div class="ev-judge-badges">${badges}<span class="ev-judge-badge ok">overall ${row.score!=null?Number(row.score).toFixed(2):'—'}</span></div>
    ${row.judge_reasoning?`<div class="muted" style="font-size:12px;margin-top:8px">${global.escAi(row.judge_reasoning)}</div>`:''}
    ${viol}${fbBar}
    </div>`;
  }

  let _evalModalCaseId = null;
  let _evalFbVerdict = null;

  global.selectEvalFeedbackVerdict = function(verdict){
    _evalFbVerdict = verdict;
    const agree = $('evalFbAgree');
    const disagree = $('evalFbDisagree');
    if(agree) agree.classList.toggle('verdict-active', verdict === 'agree');
    if(disagree) disagree.classList.toggle('verdict-active', verdict === 'disagree');
    const l3 = groupEvalCaseRows(_evalCases)[_evalModalCaseId]?.layers[3];
    const scoreWrap = $('evalFbScoreWrap');
    const scoreEl = $('evalFbScore');
    const hint = $('evalFbScoreHint');
    if(verdict === 'agree'){
      const j = judgeOverallInt(l3?.score);
      if(scoreWrap) scoreWrap.style.display = 'none';
      if(hint) hint.textContent = j != null ? `已采用 judge overall（${j}）` : '已采用 judge overall';
    } else {
      if(scoreWrap) scoreWrap.style.display = '';
      if(scoreEl){ scoreEl.value = ''; scoreEl.disabled = false; scoreEl.focus(); }
      if(hint) hint.textContent = '请给出你认为的分数，用于校准裁判';
    }
  };

  global.openEvalCaseModal = function(caseId){
    _evalModalCaseId = caseId;
    _evalFbVerdict = null;
    const group = groupEvalCaseRows(_evalCases)[caseId];
    if(!group) return;
    $('evalCaseModalTitle').textContent = `${caseId} · ${group.query||''}`;
    const l3 = group.layers[3];
    const traceId = (l3&&l3.actual&&l3.actual.agent_run_id)
      || (group.layers[2]&&group.layers[2].actual&&group.layers[2].actual.agent_run_id)
      || (group.layers[1]&&group.layers[1].actual&&group.layers[1].actual.agent_run_id);
    const traceLink = $('evalCaseTraceLink');
    if(traceId && traceLink){
      traceLink.style.display = '';
      traceLink.href = `/api/v1/agent/harness/runs/${encodeURIComponent(traceId)}`;
      traceLink.title = traceId;
    } else if(traceLink){
      traceLink.style.display = 'none';
    }
    const declared = group.declared_layers || [1];
    $('evalCaseModalBody').innerHTML =
      renderEvalLayer1Block(group.layers[1], declared)+
      renderEvalLayer2Block(group.layers[2], declared)+
      renderEvalLayer3Block(group.layers[3], declared);
    global.openModal('evalCaseModal');
  };

  global.submitEvalFeedback = async function(){
    const l3 = groupEvalCaseRows(_evalCases)[_evalModalCaseId]?.layers[3];
    if(!l3||!l3.id){ global.toast('无法提交反馈'); return; }
    if(!_evalFbVerdict){ global.toast('请先选择同意或不同意'); return; }
    const scoreEl = $('evalFbScore');
    const noteEl = $('evalFbNote');
    let human = null;
    if(_evalFbVerdict === 'disagree'){
      const humanRaw = scoreEl && scoreEl.value ? parseInt(scoreEl.value, 10) : null;
      if(humanRaw == null || Number.isNaN(humanRaw)){
        global.toast('请填写人工分（1–5）');
        if(scoreEl) scoreEl.focus();
        return;
      }
      if(humanRaw < 1 || humanRaw > 5){
        global.toast('人工分须为 1–5');
        return;
      }
      human = humanRaw;
    }
    try{
      await global.apiPost('/admin/eval/feedback', {
        case_result_id: l3.id,
        verdict: _evalFbVerdict,
        human_overall: human,
        note: noteEl ? noteEl.value : '',
      });
      global.toast('反馈已记录，校准卡已更新');
      closeModal('evalCaseModal');
      if(_evalSelectedRunId) selectEvalRun(_evalSelectedRunId);
    }catch(e){ global.toast(e.message); }
  };

  global.openEvalCoverageModal = async function(){
    const body = $('evalCoverageBody');
    if(!body) return;
    body.innerHTML = '<div class="rv-empty">加载中…</div>';
    global.openModal('evalCoverageModal');
    try{
      const data = await global.apiGet('/admin/eval/coverage');
      const matrix = data.matrix||{};
      const intents = data.intents||Object.keys(matrix);
      const layers = data.layers||['L1','L2','L3'];
      const matrixHtml = `<div class="rv-section-title">意图 × 层</div><div class="table-wrap"><table class="sheet-table"><thead><tr><th>意图</th>${layers.map(l=>`<th>${l}</th>`).join('')}</tr></thead><tbody>
        ${intents.map(intent=>{
          const row = matrix[intent]||{};
          return `<tr><td>${global.escAi(intent)}</td>${layers.map(l=>{
            const n = row[l]||0;
            return `<td class="${n===0?'ev-cov-zero':''}">${n}</td>`;
          }).join('')}</tr>`;
        }).join('')}
      </tbody></table></div>`;
      const missGroups = (data.completeness&&data.completeness.groups)||[];
      const fieldTitles = {
        answer_points: 'answer_points',
        forbid: 'forbid',
        metric_callouts: 'metric_callouts',
      };
      const fieldHints = {
        answer_points: 'grader 完整性评分无参照',
        forbid: '合规红线维度无法检查',
        metric_callouts: '口径标注无人校验',
      };
      const compHtml = missGroups.length
        ? `<div class="rv-section-title" style="margin-top:16px">expected 完备度</div>
          ${missGroups.map(g=>{
            const title = fieldTitles[g.field]||g.field;
            if(g.complete){
              return `<div class="ev-cov-complete" style="margin-bottom:10px">缺 ${global.escAi(title)} 的用例（0 条）· 已完备</div>`;
            }
            return `<div style="margin-bottom:12px">
              <div><strong>缺 ${global.escAi(title)} 的用例（${g.count||g.missing.length} 条）</strong></div>
              <div class="muted" style="font-size:11px;margin:4px 0 6px">${global.escAi(fieldHints[g.field]||'')}</div>
              <div>${(g.missing||[]).map(id=>global.escAi(id)).join(', ')}</div>
            </div>`;
          }).join('')}`
        : '<div class="ev-cov-complete" style="margin-top:16px">expected 字段完备</div>';
      const glossary = `<div class="muted" style="margin-top:16px;font-size:12px;line-height:1.6"><strong>名词解释</strong> · assertion = 确定性代码断言（Layer1/2） · grader = 模型裁判 LLM-as-judge（Layer3） · 校准 = 裁判与人工评分一致率</div>`;
      body.innerHTML = matrixHtml + compHtml + glossary;
    }catch(e){
      body.innerHTML = `<div class="rv-empty rv-empty-error" onclick="openEvalCoverageModal()" style="cursor:pointer">${global.escAi(e.message)} · 点击重试</div>`;
    }
  };

  async function loadEvalPage(){
    const listHost = $('evalRunList');
    const detailHost = $('evalRunDetail');
    if(!listHost) return;
    const triggerWrap = $('evalTriggerWrap');
    if(triggerWrap) triggerWrap.style.display = canOperateTickets()?'flex':'none';
    listHost.innerHTML = '<div class="rv-empty">加载中…</div>';
    try{
      try{ await global.apiPost('/admin/eval/seed-demo', { force: false }); }catch(_e){ /* ignore */ }
      if(canOperateTickets()){
        try{ await global.apiPost('/admin/eval/runs/cleanup-garbage', {}); }catch(_e){ /* ignore */ }
      }
      const data = await global.apiGet('/admin/eval/runs?limit=20');
      const items = data.items||[];
      if(!items.length){
        listHost.innerHTML = '<div class="rv-empty">暂无跑批记录</div>';
        if(detailHost) detailHost.innerHTML = '<div class="rv-empty">技术超管可点击上方按钮触发评测</div>';
        return;
      }
      listHost.innerHTML = items.map(r=>{
        const active = r.id===_evalSelectedRunId?' active':'';
        const plannerTxt = r.planner_accuracy!=null ? ` planner ${(r.planner_accuracy*100).toFixed(1)}%` : '';
        const demoTag = r.trigger==='demo' ? '<span class="ev-demo-tag">demo</span>' : '';
        const timeTxt = global.escAi((r.started_at||'').replace('T',' ').slice(0,16));
        return `<div class="ev-run-item${active}" onclick="selectEvalRun(${r.id})">
          <div class="ev-run-head">
            <span class="ev-run-id">#${r.id}</span>
            ${demoTag}<span class="ev-run-ver">${global.escAi(r.version||'—')}</span>
            ${evalStatusBadge(r.status)}
          </div>
          <div class="ev-run-meta">${evalRunGateDot(r)}${plannerTxt?`<span class="ev-run-meta-planner">${plannerTxt.trim()}</span>`:''}<span class="ev-run-time">${timeTxt}</span></div>
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
      const [r, casesRes, diffRes] = await Promise.all([
        global.apiGet('/admin/eval/runs/'+runId, {include_cases:false}),
        global.apiGet('/admin/eval/runs/'+runId+'/cases'),
        global.apiGet('/admin/eval/runs/'+runId+'/diff'),
      ]);
      _evalCases = casesRes.items||[];
      _evalMetrics = casesRes.metrics||{};
      _evalDiff = diffRes;
      _evalCurrentRun = r;
      _evalRunProfile = r.eval_profile || 'full';
      _evalCaseFilter = 'all';
      detailHost.innerHTML = renderEvalReport(r, diffRes, _evalMetrics);
      bindEvalCaseTableClicks();
    }catch(e){
      detailHost.innerHTML = `<div class="rv-empty rv-empty-error" onclick="selectEvalRun(${runId})" style="cursor:pointer">加载失败，点击重试 · ${global.escAi(e.message)}</div>`;
    }
  };

  let _evalTriggerOnlyLayer1 = false;

  global.triggerEvalRun = function(onlyLayer1){
    if(!canOperateTickets()){ global.toast('仅技术超管可触发评测'); return; }
    _evalTriggerOnlyLayer1 = !!onlyLayer1;
    const def = evalDefaultVersion();
    const titleEl = $('evalTriggerModalTitle');
    const hintEl = $('evalTriggerVersionHint');
    const submitBtn = $('evalTriggerSubmitBtn');
    const input = $('evalTriggerVersion');
    if(titleEl) titleEl.textContent = onlyLayer1 ? '快速检查 · 仅意图层' : '开始评测';
    if(hintEl) hintEl.textContent = '留空则用 '+def+'，可填 v1.4.0 等';
    if(submitBtn) submitBtn.textContent = onlyLayer1 ? '开始快速检查' : '开始评测';
    if(input){
      input.value = def;
      if(!input._evalEnterBound){
        input._evalEnterBound = true;
        input.addEventListener('keydown', ev=>{
          if(ev.key === 'Enter'){ ev.preventDefault(); global.submitEvalTriggerModal(); }
        });
      }
    }
    global.openModal('evalTriggerModal');
    setTimeout(()=>{ if(input) input.focus(); input && input.select(); }, 50);
  };

  global.submitEvalTriggerModal = async function(){
    const def = evalDefaultVersion();
    const input = $('evalTriggerVersion');
    const ver = (input && input.value ? input.value.trim() : '') || def;
    closeModal('evalTriggerModal');
    const statusEl = $('evalTriggerStatus');
    if(statusEl) statusEl.textContent = '正在启动…';
    try{
      const q = 'only_layer1='+(_evalTriggerOnlyLayer1?'true':'false')+'&version='+encodeURIComponent(ver);
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
