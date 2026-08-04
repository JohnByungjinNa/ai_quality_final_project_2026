const fs = require('fs');
const path = require('path');
const { chromium } = require(
  'C:/Users/DWIT/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright'
);

const baseDir = __dirname;
const commandPath = path.join(baseDir, 'live-command.json');
const statusPath = path.join(baseDir, 'live-status.json');

function writeStatus(payload) {
  fs.writeFileSync(
    statusPath,
    JSON.stringify({ at: new Date().toISOString(), ...payload }, null, 2),
    'utf8'
  );
}

async function ensureDemoCursor(page) {
  await page.evaluate(() => {
    if (document.getElementById('codex-demo-cursor')) return;

    const cursor = document.createElement('div');
    cursor.id = 'codex-demo-cursor';
    cursor.innerHTML = '<span class="codex-demo-dot"></span><span class="codex-demo-label">Codex</span>';
    cursor.style.cssText = [
      'position:fixed',
      'left:24px',
      'top:24px',
      'z-index:2147483647',
      'pointer-events:none',
      'display:flex',
      'align-items:center',
      'gap:8px',
      'transition:left 900ms cubic-bezier(.22,.8,.3,1), top 900ms cubic-bezier(.22,.8,.3,1)',
    ].join(';');

    cursor.querySelector('.codex-demo-dot').style.cssText = [
      'display:block',
      'width:22px',
      'height:22px',
      'box-sizing:border-box',
      'border-radius:50%',
      'background:#ef233c',
      'border:4px solid white',
      'box-shadow:0 0 0 4px rgba(239,35,60,.38),0 4px 14px rgba(0,0,0,.38)',
      'transition:transform 160ms ease',
    ].join(';');
    cursor.querySelector('.codex-demo-label').style.cssText = [
      'display:block',
      'padding:5px 9px',
      'border-radius:999px',
      'background:#c9182b',
      'color:white',
      'font:700 12px/1.2 "Segoe UI",sans-serif',
      'box-shadow:0 3px 10px rgba(0,0,0,.28)',
      'white-space:nowrap',
    ].join(';');
    document.body.appendChild(cursor);
  });
}

async function showDemoStep(page, title, detail) {
  await page.evaluate(({ title, detail }) => {
    let hud = document.getElementById('codex-demo-hud');
    if (!hud) {
      hud = document.createElement('div');
      hud.id = 'codex-demo-hud';
      hud.innerHTML = '<strong></strong><span></span>';
      hud.style.cssText = [
        'position:fixed',
        'left:50%',
        'top:14px',
        'transform:translateX(-50%)',
        'z-index:2147483646',
        'pointer-events:none',
        'display:flex',
        'align-items:center',
        'gap:12px',
        'min-width:520px',
        'max-width:80vw',
        'padding:12px 18px',
        'border:1px solid rgba(255,255,255,.72)',
        'border-radius:14px',
        'background:rgba(13,71,161,.96)',
        'color:white',
        'box-shadow:0 8px 24px rgba(0,0,0,.28)',
        'font-family:"Segoe UI",sans-serif',
      ].join(';');
      hud.querySelector('strong').style.cssText =
        'font-size:14px;white-space:nowrap;color:#fff';
      hud.querySelector('span').style.cssText =
        'font-size:13px;color:#dbeafe;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
      document.body.appendChild(hud);
    }
    hud.querySelector('strong').textContent = title;
    hud.querySelector('span').textContent = detail;
  }, { title, detail });
}

async function showDemoFinale(page, options = {}) {
  const finalState = options.finalState || 'BUSINESS_APPROVED';
  await page.evaluate(({ finalState }) => {
    document.getElementById('codex-demo-finale')?.remove();
    const finale = document.createElement('div');
    finale.id = 'codex-demo-finale';
    finale.innerHTML = `
      <div class="codex-finale-glow"></div>
      <div class="codex-finale-check">✓</div>
      <h1>VOC 품질진단 시연 완료</h1>
      <p class="codex-finale-flow">Pipeline → 독립 평가 → 타당성 검증 → QA 검토 → 업무 승인</p>
      <strong class="codex-finale-state">${finalState}</strong>
      <section class="codex-finale-purpose">
        <span>WHY THIS PROCESS</span>
        <h2>좋은 개선안을 넘어, 실행 가능한 개선안만 승인합니다.</h2>
        <p>
          VOC 분석 결과가 실제 업무 변화로 이어지려면 근거뿐 아니라 담당·일정·KPI·적용 범위와
          리스크까지 검증되어야 합니다. 그래서 타당성 평가를 독립 Judge와 사람 승인 사이의 핵심 Gate로 설계했습니다.
        </p>
        <div class="codex-finale-goals">
          <article><b>01 · 근거 연결</b><small>VOC 원문·Run·Trace로 판단을 재현</small></article>
          <article><b>02 · 실행 가능성</b><small>담당·일정·KPI·리스크를 정량 검증</small></article>
          <article><b>03 · 책임 있는 적용</b><small>QA와 업무 승인으로 운영 책임을 확정</small></article>
        </div>
        <blockquote>
          이 프로젝트의 목표는 AI가 그럴듯한 답을 만드는 데서 끝내지 않고,<br>
          실제로 실행하고 측정하며 책임질 수 있는 개선안만 운영으로 연결하는 것입니다.
        </blockquote>
      </section>
      <div class="codex-finale-confetti"></div>
    `;
    finale.style.cssText = [
      'position:fixed',
      'inset:0',
      'z-index:2147483647',
      'display:flex',
      'flex-direction:column',
      'align-items:center',
      'justify-content:center',
      'overflow:hidden',
      'background:radial-gradient(circle at 50% 30%,rgba(59,130,246,.4),transparent 38%),linear-gradient(135deg,#061a3a,#0d47a1 55%,#087f5b)',
      'color:white',
      'font-family:"Segoe UI","Malgun Gothic",sans-serif',
      'text-align:center',
      'animation:codexFinaleIn .55s ease-out both',
    ].join(';');
    const style = document.createElement('style');
    style.textContent = `
      @keyframes codexFinaleIn{from{opacity:0;transform:scale(1.04)}to{opacity:1;transform:scale(1)}}
      @keyframes codexFinalePulse{0%,100%{transform:scale(1);box-shadow:0 0 35px rgba(74,222,128,.45)}50%{transform:scale(1.08);box-shadow:0 0 85px rgba(74,222,128,.9)}}
      @keyframes codexConfettiFall{0%{transform:translateY(-15vh) rotate(0deg);opacity:1}100%{transform:translateY(115vh) rotate(720deg);opacity:.1}}
      #codex-demo-finale .codex-finale-check{width:88px;height:88px;border:4px solid rgba(255,255,255,.9);border-radius:50%;display:grid;place-items:center;background:linear-gradient(145deg,#22c55e,#087f5b);font-size:56px;font-weight:900;line-height:1;animation:codexFinalePulse 1.4s ease-in-out infinite}
      #codex-demo-finale h1{margin:18px 0 5px;font-size:43px;letter-spacing:-1.6px;text-shadow:0 6px 24px rgba(0,0,0,.35)}
      #codex-demo-finale .codex-finale-flow{margin:0 0 12px;font-size:17px;color:#dbeafe;font-weight:650}
      #codex-demo-finale .codex-finale-state{padding:7px 18px;border:1px solid rgba(255,255,255,.75);border-radius:999px;background:rgba(255,255,255,.14);font-size:17px;letter-spacing:1px;box-shadow:0 8px 30px rgba(0,0,0,.24)}
      #codex-demo-finale .codex-finale-purpose{position:relative;width:min(980px,86vw);margin-top:20px;padding:19px 24px 17px;border:1px solid rgba(191,219,254,.34);border-radius:20px;background:linear-gradient(145deg,rgba(4,30,66,.82),rgba(6,78,78,.68));box-shadow:0 18px 48px rgba(0,0,0,.24);backdrop-filter:blur(10px)}
      #codex-demo-finale .codex-finale-purpose>span{display:inline-block;color:#86efac;font-size:10px;font-weight:900;letter-spacing:2px}
      #codex-demo-finale .codex-finale-purpose h2{margin:6px 0 7px;color:#fff;font-size:25px;letter-spacing:-.7px}
      #codex-demo-finale .codex-finale-purpose>p{max-width:850px;margin:0 auto;color:#cfe3f8;font-size:13px;line-height:1.55;font-weight:500}
      #codex-demo-finale .codex-finale-goals{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0 12px}
      #codex-demo-finale .codex-finale-goals article{padding:10px 12px;border:1px solid rgba(191,219,254,.24);border-radius:12px;background:rgba(255,255,255,.08);text-align:left}
      #codex-demo-finale .codex-finale-goals b{display:block;color:#fff;font-size:12px}
      #codex-demo-finale .codex-finale-goals small{display:block;margin-top:4px;color:#bfdbfe;font-size:10px;line-height:1.35}
      #codex-demo-finale blockquote{margin:0;padding:10px 14px;border-left:4px solid #4ade80;border-radius:7px;background:rgba(5,46,22,.32);color:#ecfdf5;font-size:14px;font-weight:750;line-height:1.45}
      #codex-demo-finale .codex-finale-glow{position:absolute;width:520px;height:520px;border-radius:50%;border:2px solid rgba(255,255,255,.12);box-shadow:0 0 120px rgba(96,165,250,.38)}
      @media(max-height:760px){#codex-demo-finale .codex-finale-check{width:68px;height:68px;font-size:43px}#codex-demo-finale h1{margin-top:10px;font-size:35px}#codex-demo-finale .codex-finale-purpose{margin-top:12px;padding:13px 18px}#codex-demo-finale .codex-finale-purpose h2{font-size:21px}#codex-demo-finale .codex-finale-goals{margin:9px 0}#codex-demo-finale blockquote{padding:7px 12px;font-size:12px}}
    `;
    finale.appendChild(style);
    const confetti = finale.querySelector('.codex-finale-confetti');
    const colors = ['#ffffff', '#60a5fa', '#4ade80', '#facc15', '#f472b6'];
    for (let i = 0; i < 90; i += 1) {
      const piece = document.createElement('i');
      const size = 5 + Math.random() * 9;
      piece.style.cssText = [
        'position:absolute',
        `left:${Math.random() * 100}%`,
        `top:${-10 - Math.random() * 40}%`,
        `width:${size}px`,
        `height:${size * 1.7}px`,
        `background:${colors[i % colors.length]}`,
        `animation:codexConfettiFall ${3.5 + Math.random() * 3}s linear ${Math.random() * 2}s infinite`,
      ].join(';');
      confetti.appendChild(piece);
    }
    document.body.appendChild(finale);
  }, { finalState });
  await page.waitForTimeout(options.holdMs || 8000);
  await page.evaluate(() => document.getElementById('codex-demo-finale')?.remove());
}

async function showScenarioOverview(page, holdMs = 18000) {
  const steps = [
    ['01', 'Dashboard', '환경·Agent·Run·Judge·결함 요약'],
    ['02', 'Agent 전체 시작', '6개 Agent 기동과 진행 로그'],
    ['03', '품질 평가 기준', '3개 탭의 세부 배점 팝업'],
    ['04', 'TC-01 Pipeline', '실시간 화면을 완료까지 고정 관찰'],
    ['05', '독립성 보완', '다른 Provider로 동일 결과 재평가'],
    ['06', '최신 수행 이력', '방금 생성한 Run 상세 팝업'],
    ['07', '초안작성 마법사', 'Run·Case·Trace 기반 보완 초안 생성'],
    ['08', '타당성 평가', '실제 AI_PASS와 보류 규칙 확인'],
    ['09', 'QA 검토', 'QA_REVIEWED 감사 이력 저장'],
    ['10', '업무 승인', 'BUSINESS_APPROVED 정식 승인'],
    ['11', '시연 종료', '전체 화면 체크와 콘페티'],
    ['12', '부가기능', 'Jira·GitHub·AWS 연동 소개'],
  ];
  await page.evaluate(({ steps }) => {
    document.getElementById('codex-scenario-overview')?.remove();
    const overlay = document.createElement('section');
    overlay.id = 'codex-scenario-overview';
    overlay.innerHTML = `
      <header>
        <span>VOC QUALITY DEMO</span>
        <h1>최종 녹화 시연 흐름</h1>
        <p><b>목적</b> · VOC 개선 판단을 객관적인 품질 기준과 추적 가능한 증적 체인으로 표준화합니다.</p>
        <p><b>기대효과</b> · 판단 편차와 근거 누락을 줄이고, 실행 가능한 개선안·감사 이력·업무 연계를 확보합니다.</p>
      </header>
      <main>${steps.map(([number, title, detail]) => `
        <article>
          <b>${number}</b>
          <div><strong>${title}</strong><small>${detail}</small></div>
        </article>
      `).join('')}</main>
      <footer>
        <i></i>
        <span>기능 완료 후 이 순서로 중단 없이 녹화합니다.</span>
        <em>PREVIEW</em>
      </footer>
    `;
    overlay.style.cssText = [
      'position:fixed',
      'inset:0',
      'z-index:2147483647',
      'overflow:hidden',
      'box-sizing:border-box',
      'padding:42px 62px 30px',
      'background:radial-gradient(circle at 85% 12%,rgba(37,99,235,.35),transparent 34%),linear-gradient(145deg,#05142f,#082b59 60%,#0b5f58)',
      'color:white',
      'font-family:"Segoe UI","Malgun Gothic",sans-serif',
      'animation:codexScenarioIn .5s ease-out both',
    ].join(';');
    const style = document.createElement('style');
    style.textContent = `
      @keyframes codexScenarioIn{from{opacity:0;transform:scale(1.025)}to{opacity:1;transform:scale(1)}}
      @keyframes codexScenarioGlow{0%,100%{opacity:.55}50%{opacity:1}}
      #codex-scenario-overview header span{display:inline-block;padding:5px 11px;border:1px solid rgba(147,197,253,.65);border-radius:999px;color:#bfdbfe;font-size:11px;font-weight:800;letter-spacing:1.5px}
      #codex-scenario-overview h1{margin:12px 0 5px;font-size:40px;line-height:1.05;letter-spacing:-1.6px}
      #codex-scenario-overview header p{margin:4px 0 0;color:#c8dcf5;font-size:14px}
      #codex-scenario-overview header p b{color:#86efac;margin-right:4px}
      #codex-scenario-overview main{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px;margin-top:25px}
      #codex-scenario-overview article{display:flex;align-items:center;gap:12px;min-height:78px;padding:12px 14px;border:1px solid rgba(191,219,254,.28);border-radius:13px;background:linear-gradient(145deg,rgba(255,255,255,.12),rgba(255,255,255,.055));box-shadow:0 10px 28px rgba(0,0,0,.15);backdrop-filter:blur(8px)}
      #codex-scenario-overview article b{display:grid;place-items:center;flex:0 0 39px;width:39px;height:39px;border-radius:11px;background:#1d4ed8;color:white;font-size:14px;box-shadow:0 0 24px rgba(96,165,250,.45)}
      #codex-scenario-overview article:nth-child(n+8) b{background:#087f5b;box-shadow:0 0 24px rgba(74,222,128,.38)}
      #codex-scenario-overview article strong{display:block;font-size:14px;color:white}
      #codex-scenario-overview article small{display:block;margin-top:4px;color:#c8dcf5;font-size:11px;line-height:1.35}
      #codex-scenario-overview footer{position:absolute;left:62px;right:62px;bottom:25px;display:flex;align-items:center;gap:10px;padding-top:14px;border-top:1px solid rgba(255,255,255,.2);color:#dbeafe;font-size:13px}
      #codex-scenario-overview footer i{width:9px;height:9px;border-radius:50%;background:#4ade80;box-shadow:0 0 18px #4ade80;animation:codexScenarioGlow 1.2s ease-in-out infinite}
      #codex-scenario-overview footer em{margin-left:auto;padding:5px 10px;border-radius:7px;background:rgba(255,255,255,.1);font-style:normal;font-size:10px;font-weight:850;letter-spacing:1px}
    `;
    overlay.appendChild(style);
    document.body.appendChild(overlay);
  }, { steps });
  await page.waitForTimeout(holdMs);
  await page.evaluate(() => document.getElementById('codex-scenario-overview')?.remove());
}

async function ensureAllAgentsRunning(page) {
  await showDemoStep(
    page,
    '1/7 · Agent 실행 사전 점검',
    'Pipeline 시작 전에 6개 Agent 상태를 확인하고, 중지된 Agent가 있으면 전체 시작으로 복구합니다.'
  );
  const stoppedAgentButtons = page.locator('div[class*="st-key-start_agent_"] button');
  if ((await stoppedAgentButtons.count()) > 0) {
    const confirmation = page.getByRole('checkbox', { name: 'Agent 프로세스 상태 변경' });
    if (!(await confirmation.isChecked())) {
      await recordingClick(page, confirmation, 'Agent 상태 변경 확인', 1000);
    }
    await recordingClick(
      page,
      page.getByRole('button', { name: '전체 시작', exact: true }),
      '6개 Agent 전체 시작',
      1500
    );
  }

  const startedAt = Date.now();
  while (Date.now() - startedAt < 90000) {
    const runningCount = await page.locator('div[class*="st-key-stop_agent_"] button').count();
    const stoppedCount = await stoppedAgentButtons.count();
    if (runningCount === 6 && stoppedCount === 0) {
      await showDemoStep(
        page,
        '1/7 · Agent 준비 완료',
        'Interpreter부터 Improver까지 6개 Agent가 모두 RUNNING입니다. 이제 Pipeline을 안전하게 실행합니다.'
      );
      await page.waitForTimeout(1800);
      return;
    }
    await showDemoStep(
      page,
      `1/7 · Agent 기동 확인 중 · ${Math.round((Date.now() - startedAt) / 1000)}초`,
      `현재 ${runningCount}/6 RUNNING · 모든 Agent가 준비될 때까지 Pipeline을 시작하지 않습니다.`
    );
    await page.waitForTimeout(1500);
  }
  throw new Error('Agent 사전 점검 실패: 90초 안에 6개 Agent가 모두 RUNNING 상태가 되지 않았습니다.');
}

async function showRubricDetailDialog(page, rubricType, stageLabel) {
  const table = page.locator(`div[class*="st-key-rubric_edit_${rubricType}_widget_item_table"]`);
  await pointAt(page, table, `${stageLabel} · 평가 항목 선택`, 1400);
  const canvas = table.locator('[data-testid="stDataFrame"] canvas').first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error(`${stageLabel} 세부 배점 표를 찾지 못했습니다.`);
  await page.mouse.click(
    box.x + Math.min(170, box.width * 0.35),
    box.y + Math.min(65, box.height * 0.3)
  );
  const dialogTitle = page.getByText('세부 배점 설정', { exact: true }).last();
  await dialogTitle.waitFor({ state: 'visible', timeout: 10000 });
  await safePointAt(page, dialogTitle, `${stageLabel} · 세부 배점 설정`, 1600, 5000);
  await safePointAt(
    page,
    page.locator(`div[class*="st-key-rubric_criteria_panel_${rubricType}_"]`).first(),
    '세부 기준별 배점과 통과 하한',
    2200,
    5000
  );
  await recordingClick(
    page,
    page.locator(`div[class*="st-key-rubric_detail_done_${rubricType}_"] button`).first(),
    '설정 완료',
    1000
  );
  await dialogTitle.waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(900);
}

async function selectRubricStage(page, index, rubricType, stageLabel) {
  const optionText = {
    internal_pipeline: '내부 파이프라인 품질',
    independent_judge: '독립 LLM 평가',
    improvement_validity: '개선안 타당성 평가',
  }[rubricType];
  const targetTable = page.locator(
    `div[class*="st-key-rubric_edit_${rubricType}_widget_item_table"]`
  );
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    await recordingClick(
      page,
      page.getByText(optionText, { exact: true }).first(),
      `${stageLabel} 탭`,
      attempt === 1 ? 1200 : 500
    );
    const visible = await targetTable
      .waitFor({ state: 'visible', timeout: 7000 })
      .then(() => true)
      .catch(() => false);
    if (visible) return;
    await page.waitForTimeout(900);
  }
  throw new Error(`${stageLabel} 탭 전환 후 평가 항목 표를 찾지 못했습니다.`);
}

async function pointAndClick(page, locator, label) {
  locator = locator.first();
  await locator.waitFor({ state: 'visible' });
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error(`Cannot point to target: ${label}`);

  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await ensureDemoCursor(page);
  await page.evaluate(({ x, y, label }) => {
    const cursor = document.getElementById('codex-demo-cursor');
    cursor.querySelector('.codex-demo-label').textContent = label;
    cursor.style.left = `${x - 11}px`;
    cursor.style.top = `${y - 11}px`;
  }, { x, y, label });
  await page.mouse.move(x, y, { steps: 24 });
  await page.waitForTimeout(1100);
  await page.evaluate(() => {
    const dot = document.querySelector('#codex-demo-cursor .codex-demo-dot');
    if (dot) dot.style.transform = 'scale(.55)';
  });
  await page.waitForTimeout(180);
  await locator.click();
  await page.waitForTimeout(280);
  await ensureDemoCursor(page);
  await page.evaluate(() => {
    const dot = document.querySelector('#codex-demo-cursor .codex-demo-dot');
    if (dot) dot.style.transform = 'scale(1)';
  });
}

async function pointAt(page, locator, label, dwellMs = 2600, timeoutMs = 15000) {
  locator = locator.first();
  await locator.waitFor({ state: 'visible', timeout: timeoutMs });
  await locator.evaluate((element) => {
    element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
  });
  await page.waitForTimeout(1300);
  const box = await locator.boundingBox();
  if (!box) throw new Error(`Cannot point to target: ${label}`);

  const x = box.x + Math.min(box.width / 2, Math.max(24, box.width * 0.35));
  const y = box.y + box.height / 2;
  await ensureDemoCursor(page);
  await page.evaluate(({ x, y, label }) => {
    const cursor = document.getElementById('codex-demo-cursor');
    cursor.querySelector('.codex-demo-label').textContent = label;
    cursor.style.left = `${x - 11}px`;
    cursor.style.top = `${y - 11}px`;
  }, { x, y, label });
  await page.mouse.move(x, y, { steps: 32 });
  await locator.evaluate((element) => {
    element.dataset.codexDemoOutline = element.style.outline || '';
    element.dataset.codexDemoOffset = element.style.outlineOffset || '';
    element.style.outline = '4px solid rgba(239,35,60,.78)';
    element.style.outlineOffset = '4px';
  }).catch(() => {});
  await page.waitForTimeout(dwellMs);
  await locator.evaluate((element) => {
    element.style.outline = element.dataset.codexDemoOutline || '';
    element.style.outlineOffset = element.dataset.codexDemoOffset || '';
    delete element.dataset.codexDemoOutline;
    delete element.dataset.codexDemoOffset;
  }).catch(() => {});
}

async function recordingClick(page, locator, label, dwellMs = 2200) {
  await pointAt(page, locator, `${label} · 클릭`, dwellMs);
  locator = locator.first();
  await page.evaluate(() => {
    const dot = document.querySelector('#codex-demo-cursor .codex-demo-dot');
    if (dot) dot.style.transform = 'scale(.52)';
  });
  await page.waitForTimeout(220);
  await locator.click();
  await page.waitForTimeout(450);
  await ensureDemoCursor(page);
  await page.evaluate(() => {
    const dot = document.querySelector('#codex-demo-cursor .codex-demo-dot');
    if (dot) dot.style.transform = 'scale(1)';
  });
}

async function recordingScroll(page, deltaY, title, detail, dwellMs = 2200) {
  await ensureDemoCursor(page);
  await showDemoStep(page, title, detail);
  await page.mouse.move(1180, 650, { steps: 18 });
  await page.mouse.wheel(0, deltaY);
  await page.waitForTimeout(1200);
  await page.mouse.wheel(0, deltaY > 0 ? 260 : -260);
  await page.waitForTimeout(dwellMs);
}

async function safePointAt(page, locator, label, dwellMs = 2200, timeoutMs = 15000) {
  try {
    await pointAt(page, locator, label, dwellMs, timeoutMs);
    return true;
  } catch {
    return false;
  }
}

async function runRecordingCountdown(page) {
  for (let count = 5; count >= 1; count -= 1) {
    await ensureDemoCursor(page);
    await showDemoStep(
      page,
      `VOC 품질진단 녹화 시연 · ${count}`,
      '지금부터 마우스 이동·클릭·스크롤을 포함한 전체 시연을 연속 진행합니다.'
    );
    await page.waitForTimeout(1000);
  }
}

async function waitForStreamlitReady(page, anchor, options = {}) {
  const timeoutMs = options.timeoutMs || 30000;
  const stableMs = options.stableMs || 700;
  const startedAt = Date.now();
  await anchor.first().waitFor({ state: 'visible', timeout: timeoutMs });
  await page.waitForTimeout(350);
  let stableSince = 0;
  while (Date.now() - startedAt < timeoutMs) {
    const busy = await page.evaluate(() => {
      const visible = (element) => {
        const style = window.getComputedStyle(element);
        const box = element.getBoundingClientRect();
        return style.visibility !== 'hidden' && style.display !== 'none' && box.width > 0 && box.height > 0;
      };
      return Array.from(document.querySelectorAll('[data-testid="stSpinner"]')).some(visible);
    });
    if (!busy) {
      if (!stableSince) stableSince = Date.now();
      if (Date.now() - stableSince >= stableMs) return Date.now() - startedAt;
    } else {
      stableSince = 0;
    }
    await page.waitForTimeout(150);
  }
  throw new Error(`Streamlit page readiness timeout after ${timeoutMs}ms`);
}

async function warmupRecordingPages(page) {
  const timings = [];
  const warm = async (menu, subMenu, anchor, label, timeoutMs = 30000) => {
    const startedAt = Date.now();
    await page.getByText(menu, { exact: true }).first().click();
    if (subMenu) await page.getByText(subMenu, { exact: true }).first().click();
    await waitForStreamlitReady(page, anchor, { timeoutMs });
    timings.push({ label, elapsedMs: Date.now() - startedAt });
  };

  await showDemoStep(
    page,
    '시연 사전 준비 · 페이지 로딩',
    '녹화 전 조회 화면과 외부 연동 상태를 미리 불러와 본 시연의 대기 시간을 줄입니다.'
  );
  await warm('Jira관리', 'Jira 현황', page.locator('div[class*="st-key-jira_list_filter_bar"]'), 'Jira', 35000);
  await warm('GitHub 관리', '저장소 현황', page.locator('.gh-repo-hero'), 'GitHub 저장소');
  await warm('GitHub 관리', '프로젝트 동기화', page.getByText('프로젝트 저장·다운로드', { exact: true }), 'GitHub 동기화');
  await warm('종합 현황', 'AI QA 종합 현황', page.locator('.aqd-integration-row'), 'AWS·종합 현황');
  await warm('VOC 품질진단', '최종 인수·시연', page.locator('div[class*="st-key-acceptance_aws_evidence_actions"]'), 'AWS 인수 증적', 45000);
  await warm('VOC 품질진단', '개선안 타당성 검증', page.locator('div[class*="st-key-voc_validity_candidate_query"] input'), '타당성 검증');
  await warm('VOC 품질진단', 'Dashboard', page.locator('.vqd-status-row'), 'VOC Dashboard');
  await showDemoStep(
    page,
    '시연 사전 준비 완료',
    timings.map((item) => `${item.label} ${(item.elapsedMs / 1000).toFixed(1)}초`).join(' · ')
  );
  await page.waitForTimeout(1800);
  return timings;
}

async function runIntegrationShowcase(page, options = {}) {
  const { returnToVocDashboard = true, performAwsUpload = false } = options;

  await showDemoStep(
    page,
    '부가기능 1/3 · Jira 연동',
    'JQL 기반 이슈 조회, 신규 이슈 등록과 앱 등록 이력을 한 화면 흐름으로 관리합니다.'
  );
  await recordingClick(page, page.getByText('Jira관리', { exact: true }), 'Jira 관리', 1400);
  await waitForStreamlitReady(page, page.locator('div[class*="st-key-jira_list_filter_bar"]'));
  await safePointAt(
    page,
    page.locator('div[class*="st-key-jira_list_filter_bar"]'),
    'JQL 조회 · Search · Create',
    2800,
    5000
  );
  await recordingClick(page, page.getByText('등록 이력', { exact: true }), 'Jira 등록 이력', 1200);
  await page.waitForTimeout(1600);
  await safePointAt(page, page.getByText('앱 등록 이력', { exact: true }), 'Jira 감사 이력', 2400, 5000);

  await showDemoStep(
    page,
    '부가기능 2/3 · GitHub 연동',
    '저장소·브랜치·최근 커밋과 변경 파일을 확인하고 안전한 저장·다운로드 흐름을 제공합니다.'
  );
  await recordingClick(page, page.getByText('GitHub 관리', { exact: true }), 'GitHub 관리', 1400);
  await waitForStreamlitReady(page, page.locator('.gh-repo-hero'));
  await safePointAt(page, page.locator('.gh-repo-hero'), '저장소 · 브랜치 · 최근 커밋', 2800, 5000);
  await recordingClick(page, page.getByText('프로젝트 동기화', { exact: true }), '프로젝트 동기화', 1200);
  await waitForStreamlitReady(page, page.getByText('프로젝트 저장·다운로드', { exact: true }));
  await safePointAt(page, page.getByText('프로젝트 저장·다운로드', { exact: true }), 'Git 저장 · 다운로드 · ZIP', 2600, 5000);
  await safePointAt(page, page.getByText('동기화 사전 점검', { exact: true }), '충돌 방지 사전 점검', 2200, 5000);

  await showDemoStep(
    page,
    '부가기능 3/3 · AWS 연동',
    '임시 AWS 세션 상태와 Run별 S3 품질 증적 업로드 이력을 비밀값 노출 없이 확인합니다.'
  );
  await recordingClick(page, page.getByText('종합 현황', { exact: true }), '종합 현황', 1400);
  await waitForStreamlitReady(page, page.locator('.aqd-integration-row'));
  await safePointAt(
    page,
    page.locator('.aqd-integration-row article[aria-label^="AWS 증적."]'),
    'AWS S3 증적 업로드 현황',
    3000,
    5000
  );
  const awsPopover = page.locator('div[class*="st-key-topbar_aws_action_"] button').first();
  if (await awsPopover.isVisible().catch(() => false)) {
    await recordingClick(page, awsPopover, 'AWS 임시 세션', 1200);
    await page.waitForTimeout(900);
    await safePointAt(page, page.getByText('AWS 연결 정보', { exact: true }), '프로필 · 리전 · 로그인 상태', 2200, 5000);
    await page.keyboard.press('Escape');
  }

  await showDemoStep(
    page,
    'AWS 증적 보관 · 최종 인수 단계로 이동',
    '종합 현황에서는 업로드 상태만 확인하고, 실제 보관 작업은 승인 증적이 생성되는 최종 인수 화면에서 수행합니다.'
  );
  await recordingClick(page, page.getByText('VOC 품질진단', { exact: true }), 'VOC 품질진단', 1200);
  await recordingClick(page, page.getByText('최종 인수·시연', { exact: true }), '최종 인수·시연', 1400);
  await waitForStreamlitReady(page, page.locator('div[class*="st-key-acceptance_aws_evidence_actions"]'), { timeoutMs: 45000 });
  await safePointAt(
    page,
    page.locator('div[class*="st-key-acceptance_aws_evidence_actions"]'),
    '최종 인수 Run · S3 업로드 · 파일 확인',
    2600,
    5000
  );

  if (performAwsUpload) {
    const uploadButton = page.locator('div[class*="st-key-acceptance_aws_upload_evidence"] button').first();
    if (!(await uploadButton.isEnabled().catch(() => false))) {
      throw new Error('AWS 임시 로그인 또는 최종 인수 증적이 없어 S3 업로드 버튼이 비활성화되었습니다.');
    }
    await showDemoStep(
      page,
      'AWS 증적 업로드 · 명시적 실행',
      '선택한 최종 인수 Run의 JSON·Markdown 2개 파일만 S3에 암호화 업로드하고 원격 SHA-256을 검증합니다.'
    );
    await recordingClick(page, uploadButton, 'S3 증적 업로드', 1800);
    const uploadSuccess = page.getByText(/증적 2개를 S3에 업로드하고 원격 SHA-256 검증을 완료했습니다/).first();
    await uploadSuccess.waitFor({ state: 'visible', timeout: 120000 });
    await safePointAt(page, uploadSuccess, 'S3 업로드 · 원격 무결성 검증 완료', 3000, 5000);
  }

  const fileButton = page.locator('div[class*="st-key-acceptance_aws_files"] button').first();
  await recordingClick(page, fileButton, '업로드 파일 확인', 1200);
  await page.waitForTimeout(800);
  const fileTable = page.locator('[data-testid="stPopoverBody"] div[data-testid="stDataFrame"]').first();
  await fileTable.waitFor({ state: 'visible', timeout: 20000 });
  await safePointAt(page, fileTable, '파일명 · 크기 · S3 객체 키 · SHA-256', 3400, 20000);
  await page.keyboard.press('Escape');

  if (returnToVocDashboard) {
    await recordingClick(page, page.getByText('VOC 품질진단', { exact: true }), 'VOC 품질진단', 1200);
    await recordingClick(page, page.getByText('Dashboard', { exact: true }), 'Dashboard', 1200);
    await page.waitForTimeout(1600);
  }
}

async function runFullRecordingDemo(page, options = {}) {
  const { continueToApproval = false } = options;
  let completedRunId = '';
  let completedTraceId = '';
  await showScenarioOverview(page, options.overviewHoldMs || 9000);
  await warmupRecordingPages(page);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await runRecordingCountdown(page);

  await showDemoStep(page, '1/7 · VOC 품질진단 진입', '상단 메뉴를 열고 Agent 관리 화면으로 이동합니다.');
  await recordingClick(page, page.getByText('VOC 품질진단', { exact: true }), 'VOC 품질진단');
  await recordingClick(page, page.getByText('Agent 관리', { exact: true }), 'Agent 관리');
  await page.waitForTimeout(1800);

  await showDemoStep(page, '1/7 · Agent 및 Provider 상태', '6개 Agent 실행 상태와 세 Provider 인증 상태를 차례로 확인합니다.');
  await ensureAllAgentsRunning(page);
  await safePointAt(
    page,
    page.locator('div[class*="st-key-check_agent_gemini_credential"] button'),
    'Gemini 인증 점검',
    2600
  );
  await recordingClick(
    page,
    page.locator('div[class*="st-key-check_agent_gemini_credential"] button'),
    'Gemini 인증 점검',
    1500
  );
  await page.waitForTimeout(3500);
  await safePointAt(page, page.getByText('최근 처리 상태', { exact: true }), 'Gemini 점검 결과', 2600);

  await recordingClick(
    page,
    page.locator('div[class*="st-key-check_agent_anthropic_credential"] button'),
    'Anthropic 인증 점검',
    1500
  );
  await page.waitForTimeout(3500);
  await safePointAt(page, page.getByText('최근 처리 상태', { exact: true }), 'Anthropic 점검 결과', 2400);

  await recordingClick(
    page,
    page.locator('div[class*="st-key-check_agent_openai_credential"] button'),
    'OpenAI 인증 점검',
    1500
  );
  await page.waitForTimeout(3500);
  await safePointAt(page, page.getByText('최근 처리 상태', { exact: true }), 'OpenAI 점검 결과', 2800);

  await showDemoStep(page, '2/7 · 품질 평가 기준', '평가 단계 탭과 Rubric 관리 입력 항목을 확인합니다.');
  await recordingClick(page, page.getByText('품질 평가 기준', { exact: true }), '품질 평가 기준');
  await page.waitForTimeout(1600);
  await showRubricDetailDialog(page, 'internal_pipeline', '내부 Pipeline 품질');
  await selectRubricStage(page, 1, 'independent_judge', '독립 LLM Judge');
  await showRubricDetailDialog(page, 'independent_judge', '독립 LLM Judge');
  await safePointAt(
    page,
    page.locator('div[class*="st-key-rubric_edit_independent_judge_widget_version"] input'),
    'Rubric 버전 입력',
    2400
  );
  await safePointAt(
    page,
    page.locator('div[class*="st-key-rubric_edit_independent_judge_widget_title"] input'),
    '기준명 입력',
    2400
  );
  await safePointAt(
    page,
    page.locator('div[class*="st-key-rubric_edit_independent_judge_widget_provider"]'),
    '기본 Judge Provider 선택',
    2400
  );
  await safePointAt(
    page,
    page.locator('div[class*="st-key-rubric_edit_independent_judge_save_state"]'),
    '변경 상태',
    1800
  );
  await safePointAt(
    page,
    page.locator('div[class*="st-key-rubric_edit_independent_judge_save"] button'),
    '평가기준 저장',
    2200
  );
  await selectRubricStage(page, 2, 'improvement_validity', '개선안 타당성');
  await showRubricDetailDialog(page, 'improvement_validity', '개선안 타당성');
  await recordingScroll(
    page,
    620,
    '2/7 · 판정 구간과 세부 배점',
    '100점 Rubric의 평가 항목·배점·PASS 및 검토 구간을 아래로 이동하며 확인합니다.',
    2600
  );
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await page.waitForTimeout(1600);

  await showDemoStep(page, '3/7 · 수동 TC 수행', '읽기 전용 Case 목록에서 선택된 Case와 판정 조건을 확인합니다.');
  await recordingClick(page, page.getByText('수동 TC 수행', { exact: true }), '수동 TC 수행');
  await page.waitForTimeout(1800);
  await safePointAt(
    page,
    page.locator('div[class*="st-key-goal_testcase_table_"]'),
    '읽기 전용 Test Case 목록',
    3000
  );
  await safePointAt(page, page.getByText('선택: TC-01', { exact: true }), '선택 Case · TC-01', 2800);
  await recordingClick(page, page.getByText('판정 기준', { exact: true }), '판정 기준 펼치기', 1800);
  await page.waitForTimeout(1800);

  await showDemoStep(page, '3/7 · Agent Pipeline 실행', '선택한 TC-01을 6개 Agent와 보완 루프로 실행합니다.');
  const runButton = page.locator('div[class*="st-key-goal_execute_"] button:not([disabled])').first();
  await recordingClick(page, runButton, 'Agent Pipeline 실행', 2200);
  await page.waitForTimeout(1800);
  await recordingClick(page, page.getByText('수동 TC 수행', { exact: true }), '실시간 상태 화면 갱신', 1200);
  await page.waitForTimeout(2200);

  const judgeButton = page.locator('div[class*="st-key-goal_judge_execute_"] button:not([disabled])').first();
  for (let elapsed = 0; elapsed < 180; elapsed += 10) {
    const judgeReady = await judgeButton.isVisible().catch(() => false);
    if (judgeReady) break;
    await showDemoStep(
      page,
      `3/7 · Pipeline 실행 중 · ${elapsed + 10}초`,
      'Interpreter → Retriever → Summarizer → Evaluator → Critic → Improver 이벤트가 실시간 갱신됩니다.'
    );
    await recordingScroll(
      page,
      elapsed % 20 === 0 ? 520 : -360,
      '3/7 · 실시간 Agent Pipeline',
      'Agent 카드와 A2A Trace 이벤트를 천천히 이동하며 확인합니다.',
      3200
    );
    await page.waitForTimeout(5000);
  }

  if (!(await judgeButton.isVisible().catch(() => false))) {
    const bodyText = await page.locator('body').innerText();
    const pipelineError = bodyText.match(/(?:파이프라인|Pipeline)[^\n]{0,80}(?:실패|오류|ERROR)/i)?.[0];
    throw new Error(
      pipelineError
        ? `Pipeline 실행 실패: ${pipelineError}`
        : 'Pipeline 완료를 확인하지 못했습니다. Agent 상태와 실행 Trace를 확인하세요.'
    );
  }

  await showDemoStep(page, '3/7 · Pipeline 결과 확인', 'Run ID, Trace, Agent 성공·실패 건수와 최종 개선안을 확인합니다.');
  await recordingScroll(page, 900, '3/7 · 실행 결과', '실시간 Pipeline 아래의 수행 결과와 증적을 확인합니다.', 3000);
  const runIdLabel = page.getByText(/Run ID:/).first();
  await safePointAt(page, runIdLabel, 'Run ID 및 증적 상태', 3000);
  const runIdText = await runIdLabel.innerText().catch(() => '');
  const resultBody = await page.locator('body').innerText();
  completedRunId = (runIdText.match(/RUN-[0-9]{8}-[0-9]{6}-[0-9]{6}-[0-9a-f]{4}/i) || [''])[0];
  completedTraceId = (resultBody.match(/(?:Trace ID|Trace)\s*[:·]?\s*([A-Za-z0-9_-]{8,})/i) || ['', ''])[1];
  await recordingScroll(page, 900, '3/7 · 최종 개선안', '요약과 정책 개선안의 책임·일정·측정 지표를 확인합니다.', 3200);

  await safePointAt(
    page,
    page.locator('div[class*="st-key-goal_TC-01_judge_select_anthropic"] button'),
    'Anthropic · Claude Haiku 선택',
    2600
  );
  await recordingClick(
    page,
    page.locator('div[class*="st-key-goal_TC-01_judge_select_anthropic"] button'),
    'Anthropic Judge 선택',
    1800
  );
  await page.waitForTimeout(1600);
  await recordingClick(
    page,
    page.locator('div[class*="st-key-goal_judge_execute_"] button:not([disabled])').first(),
    '독립 LLM 평가 실행',
    2200
  );
  for (let elapsed = 0; elapsed < 90; elapsed += 10) {
    await showDemoStep(
      page,
      `4/7 · 독립 Judge 평가 중 · ${elapsed + 10}초`,
      '저장된 동일 개선안을 별도 모델이 정확성·근거성·충실성·구체성 기준으로 평가합니다.'
    );
    await page.waitForTimeout(7000);
    const running = await page.getByText('독립 LLM 평가 진행 중', { exact: true }).isVisible().catch(() => false);
    if (!running && elapsed >= 10) break;
  }
  await recordingScroll(page, 700, '4/7 · Judge 결과', 'Provider·모델·Rubric·점수·판정과 잔여 위험을 확인합니다.', 3400);
  await safePointAt(page, page.getByText('독립 LLM 평가/판정 결과', { exact: true }), '독립 Judge 판정 결과', 3000);

  await showDemoStep(page, '5/7 · 수행 이력', 'Run ID별 결과와 저장된 Case 증적을 상세 탭으로 확인합니다.');
  await recordingClick(page, page.getByText('수행 이력', { exact: true }), '수행 이력');
  await page.waitForTimeout(2200);
  await recordingScroll(page, 560, '5/7 · 이력 요약 지표', 'PASS·검토 필요·실패·Judge 상태 집계를 확인합니다.', 2800);
  await safePointAt(page, page.getByText(/실행 상세 · RUN-/).first(), '최신 Run 상세', 2800);
  const historyInfoTab = page.getByRole('tab', { name: '실행 정보', exact: true });
  if (await historyInfoTab.isVisible().catch(() => false)) {
    await recordingClick(page, historyInfoTab, '실행 정보 탭', 1800);
    await page.waitForTimeout(1800);
    await recordingScroll(page, 520, '5/7 · 실행 정보', 'Run 설정, Judge 옵션과 Rubric 버전을 확인합니다.', 2600);
  }
  const evidenceTab = page.getByRole('tab', { name: 'Case 증적', exact: true });
  if (await evidenceTab.isVisible().catch(() => false)) {
    await recordingClick(page, evidenceTab, 'Case 증적 탭', 1800);
    await page.waitForTimeout(1800);
    await recordingScroll(page, 520, '5/7 · Case 증적', 'Pipeline·Trace·규칙·Judge 원본 증적을 확인합니다.', 2800);
  }

  if (continueToApproval) {
    if (!completedRunId) throw new Error('Pipeline 결과에서 새 Run ID를 찾지 못했습니다.');
    await showDemoStep(
      page,
      '핵심 진단 구간 완료 · 승인 흐름 계속',
      `${completedRunId}의 독립성 보완, 초안작성 마법사, QA·업무 승인을 이어서 진행합니다.`
    );
    await page.waitForTimeout(2600);
    return { runId: completedRunId, traceId: completedTraceId, caseId: 'TC-01' };
  }

  await showDemoStep(page, '6/7 · 품질 보고서', '35건 정량 분석과 결함·잔여 위험·배포 판정을 확인합니다.');
  await recordingClick(page, page.getByText('품질 보고서', { exact: true }), '품질 보고서');
  await page.waitForTimeout(2200);
  await safePointAt(page, page.getByText('EVIDENCE_DRAFT', { exact: true }), '보고서 상태 · EVIDENCE_DRAFT', 2600);
  await safePointAt(page, page.getByText('NOT_APPROVED', { exact: true }), '최종 판정 · NOT_APPROVED', 2600);
  await recordingScroll(page, 640, '6/7 · 3단계 품질평가', 'VOC 분석·내부 Agent·독립 Judge의 단계별 증적을 확인합니다.', 3000);
  await recordingScroll(page, 720, '6/7 · 전체 테스트 정량 분석', 'PASS·FAIL·ERROR·REVIEW_REQUIRED·NOT_RUN 분포를 확인합니다.', 3200);
  await recordingScroll(page, 720, '6/7 · 잔여 위험과 증적', '결함 상태, 운영 권고와 TXT·XML·HTML 증적 영역을 확인합니다.', 3000);

  await showDemoStep(page, '7/7 · 최종 인수·시연', '품질 Gate와 사용자 승인 조건을 기준으로 최종 인수 상태를 확인합니다.');
  await recordingClick(page, page.getByText('최종 인수·시연', { exact: true }), '최종 인수·시연');
  await page.waitForTimeout(2200);
  await safePointAt(page, page.getByText('HOLD', { exact: true }).first(), '최종 인수 판정 · HOLD', 3000);
  await safePointAt(page, page.getByText('4/10', { exact: true }), '충족 Gate · 4/10', 2600);
  await safePointAt(page, page.getByText('PENDING', { exact: true }), '사용자 서명 · PENDING', 2600);
  await recordingScroll(page, 720, '7/7 · 인수 Gate 상세', '미충족 Gate와 운영 권고를 아래로 이동하며 확인합니다.', 3200);
  await recordingScroll(page, 760, '7/7 · 평가 체크리스트', '동료평가 80점·교수평가 20점 증적 준비 상태를 확인합니다.', 3200);
  await recordingScroll(page, 760, '7/7 · 인수 증적 생성', '현재 HOLD 판정을 JSON·Markdown 증적으로 저장합니다.', 2600);
  const acceptanceButton = page
    .locator('div[class*="st-key-generate_voc_acceptance_"] button:not([disabled])')
    .first();
  if (await acceptanceButton.isVisible().catch(() => false)) {
    await recordingClick(page, acceptanceButton, 'Step 10 인수 증적 생성', 2400);
    await page.waitForTimeout(2200);
  }

  await ensureDemoCursor(page);
  await showDemoStep(
    page,
    'VOC 품질진단 녹화 시연 완료',
    'Pipeline·Judge·Run 이력·품질 보고서·최종 HOLD 인수 증적까지 연속 확인했습니다.'
  );
  await page.waitForTimeout(10000);
  await runIntegrationShowcase(page, { returnToVocDashboard: false, performAwsUpload: true });
  await showDemoStep(
    page,
    '부가기능 시연 완료',
    'Jira 이슈 관리 · GitHub 형상관리 · AWS S3 품질 증적 연동까지 확인했습니다.'
  );
  await page.waitForTimeout(7000);
}

async function recordingFill(page, locator, label, value, dwellMs = 1100) {
  locator = locator.first();
  await locator.scrollIntoViewIfNeeded();
  await pointAt(page, locator, label, dwellMs);
  await locator.fill(value);
  await page.waitForTimeout(650);
}

async function waitForRecordingState(page, locator, options = {}) {
  const {
    timeoutMs = 120000,
    title = '평가 처리 중',
    detail = '화면을 갱신하면서 실제 평가 결과를 기다립니다.',
  } = options;
  const startedAt = Date.now();
  let elapsedSeconds = 0;
  while (Date.now() - startedAt < timeoutMs) {
    if (await locator.first().isVisible().catch(() => false)) return true;
    elapsedSeconds = Math.round((Date.now() - startedAt) / 1000);
    await ensureDemoCursor(page);
    await showDemoStep(page, `${title} · ${elapsedSeconds}초`, detail);
    await page.waitForTimeout(4000);
  }
  return false;
}

async function waitForRecordingTask(page, runningLabel, options = {}) {
  const {
    timeoutMs = 180000,
    title = '평가 처리 중',
    detail = '화면을 갱신하면서 실제 평가 결과를 기다립니다.',
  } = options;
  const running = page.getByText(runningLabel, { exact: true }).first();
  await running.waitFor({ state: 'visible', timeout: 12000 }).catch(() => {});
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (!(await running.isVisible().catch(() => false))) return true;
    const elapsedSeconds = Math.round((Date.now() - startedAt) / 1000);
    await ensureDemoCursor(page);
    await showDemoStep(page, `${title} · ${elapsedSeconds}초`, detail);
    await page.waitForTimeout(4000);
  }
  return false;
}

async function runApprovalRecordingDemo(page, command = {}) {
  const runId = String(command.runId || '').trim();
  const caseId = String(command.caseId || 'TC-01').trim();
  const traceId = String(command.traceId || '').trim();
  const reviewer = String(command.reviewer || '시연 담당자').trim();
  if (!runId) {
    throw new Error('approval_recording_demo에는 대상 runId가 필요합니다.');
  }

  if (!command.skipWarmup) await warmupRecordingPages(page);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await showDemoStep(
    page,
    '승인 시연 1/6 · 독립성 평가 결과 확인',
    '같은 Provider로 평가해 점수는 높지만 독립성 C로 보류된 결과를 먼저 확인합니다.'
  );
  await recordingClick(
    page,
    page.getByText('수동 TC 수행', { exact: true }),
    '수동 TC 수행'
  );
  await page.waitForTimeout(1900);
  await recordingScroll(
    page,
    1650,
    '승인 시연 1/6 · 기존 Judge 결과',
    `대상 ${caseId}의 점수, 유효 판정, 독립성 등급을 확인합니다.`,
    2200
  );
  await safePointAt(
    page,
    page.getByText('독립 LLM 평가/판정 결과', { exact: true }).first(),
    '독립성 C · REVIEW_REQUIRED 확인',
    2800
  );

  await showDemoStep(
    page,
    '승인 시연 2/6 · 독립성 보완',
    '점수를 수정하지 않고 생성 모델과 다른 Gemini Judge로 동일 산출물을 다시 평가합니다.'
  );
  const geminiCard = page.locator(
    `div[class*="st-key-goal_${caseId}_judge_select_gemini"] button`
  );
  await recordingClick(page, geminiCard, 'Gemini Judge 선택', 1900);
  await page.waitForTimeout(1400);
  const judgeButton = page
    .locator('div[class*="st-key-goal_judge_execute_"] button:not([disabled])')
    .first();
  await recordingClick(page, judgeButton, '독립 LLM 재평가 실행', 2100);
  await waitForRecordingTask(page, '독립 LLM 평가 진행 중', {
    timeoutMs: command.judgeTimeoutMs || 150000,
    title: '승인 시연 2/6 · Gemini 독립 평가 중',
    detail: '동일 개선안을 다른 Provider가 재평가하여 모델 독립성을 확보합니다.',
  });
  await recordingScroll(
    page,
    720,
    '승인 시연 2/6 · 독립성 보완 결과',
    'Provider·모델·점수와 독립성 A/B 등급, 유효 판정을 함께 확인합니다.',
    2600
  );
  await safePointAt(
    page,
    page.getByText('독립 LLM 평가/판정 결과', { exact: true }).first(),
    '재평가 결과 · 독립성 A/B 확인',
    3000
  );

  await showDemoStep(
    page,
    '승인 시연 3/6 · 개선안 타당성 검증',
    '독립 평가가 끝난 Run을 검색하고 담당·일정·KPI·우선순위·근거·리스크를 보완합니다.'
  );
  await recordingClick(
    page,
    page.getByText('개선안 타당성 검증', { exact: true }),
    '개선안 타당성 검증'
  );
  await page.waitForTimeout(1900);
  const queryInput = page.locator(
    'div[class*="st-key-voc_validity_candidate_query"] input'
  );
  await recordingFill(page, queryInput, '대상 Run ID 검색', runId, 1500);
  await queryInput.press('Enter');
  await page.waitForTimeout(2200);
  await safePointAt(
    page,
    page.locator('div[class*="st-key-voc_validity_candidate_table"]'),
    `${runId} · ${caseId} 검증 대상`,
    2500
  );

  const inputExpander = page.getByText('입력 열기', { exact: true }).first();
  if (await inputExpander.isVisible().catch(() => false)) {
    await recordingClick(page, inputExpander, '보완 입력 열기', 1200);
    await page.waitForTimeout(700);
  }
  const draftWizard = page.locator('div[class*="st-key-validity_supplement_draft_"] button').first();
  await recordingClick(page, draftWizard, '초안작성 마법사 실행', 1800);
  await waitForStreamlitReady(
    page,
    page.locator(`div[class*="st-key-validity_supplement_${runId}_${caseId}_owner"] textarea`),
    { timeoutMs: 15000 }
  );
  await safePointAt(
    page,
    page.locator(`div[class*="st-key-validity_supplement_${runId}_${caseId}_owner"] textarea`),
    '마법사 초안 · 담당/오너',
    1800,
    5000
  );
  await safePointAt(
    page,
    page.locator(`div[class*="st-key-validity_supplement_${runId}_${caseId}_evidence"] textarea`),
    `마법사 초안 · Run ${runId} · Trace ${traceId || '자동 연결'}`,
    1800,
    5000
  );
  await recordingClick(
    page,
    page.getByText('사전 보완 입력 저장', { exact: true }).first(),
    '마법사 초안 확인 후 저장',
    1800
  );
  await page.waitForTimeout(2500);

  await showDemoStep(
    page,
    '승인 시연 4/6 · 자동 타당성 평가',
    '저장한 보완 근거를 포함해 현재 Rubric 기준으로 개선안의 실행 가능성과 안전성을 평가합니다.'
  );
  const validityButton = page.locator(
    `div[class*="st-key-validity_auto_evaluate_${runId}_${caseId}"] button:not([disabled])`
  );
  await recordingClick(page, validityButton, '선택 대상 자동 타당성 평가 실행', 2200);
  await waitForRecordingTask(page, '자동 타당성 평가 수행 중', {
    timeoutMs: command.validityTimeoutMs || 180000,
    title: '승인 시연 4/6 · 타당성 평가 중',
    detail: '보완 근거와 Pipeline·Trace·독립 Judge 결과를 결합해 실제 AI 판정을 산출합니다.',
  });
  const qaApproveButton = page.getByRole('button', { name: /QA 승인 저장$/ }).first();
  const qaReady = await waitForRecordingState(page, qaApproveButton, {
    timeoutMs: command.validityTimeoutMs || 180000,
    title: '승인 시연 4/6 · AI 판정 확인',
    detail: 'AI_PASS와 즉시 보류 규칙 충족 여부를 확인합니다.',
  });
  if (!qaReady) {
    await showDemoStep(
      page,
      '승인 시연 중단 · AI_PASS 미충족',
      '현재 결과가 AI_PASS 기준을 충족하지 못했습니다. 보완 권고를 반영한 뒤 다시 평가해야 하며 승인 상태는 강제로 만들지 않습니다.'
    );
    await page.waitForTimeout(8000);
    return;
  }
  const qaForm = qaApproveButton.locator('xpath=ancestor::div[@data-testid="stForm"][1]');
  await safePointAt(page, page.getByText('AI_PASS', { exact: true }).first(), '타당성 판정 · AI_PASS', 3000);

  await showDemoStep(
    page,
    '승인 시연 5/6 · QA 검토',
    'AI_PASS와 즉시 보류 없음 상태를 확인한 뒤 QA 역할로 검토 의견을 저장합니다.'
  );
  await qaForm.scrollIntoViewIfNeeded();
  await recordingFill(page, qaForm.locator('input').first(), 'QA 검토자', reviewer, 1000);
  await recordingFill(
    page,
    qaForm.locator('textarea').first(),
    'QA 검토 의견',
    '독립성 보완 결과, 타당성 점수, 즉시 보류 규칙, Run·Trace 증적을 확인하여 QA 승인합니다.',
    1200
  );
  await recordingClick(
    page,
    qaApproveButton,
    'QA 검토 결과 저장',
    1900
  );
  await page.waitForTimeout(2600);
  await safePointAt(page, page.getByText('QA 검토 완료', { exact: true }).first(), 'QA_REVIEWED 확인', 2800);

  await showDemoStep(
    page,
    '승인 시연 6/6 · 업무 승인',
    '같은 시연자가 수행하더라도 QA와 업무 역할·시각·의견은 별도 감사 이력으로 남깁니다.'
  );
  const businessApproveButton = page.getByRole('button', { name: /업무 승인 저장$/ }).first();
  const businessReady = await waitForRecordingState(page, businessApproveButton, {
    timeoutMs: 30000,
    title: '승인 시연 6/6 · 업무 승인 준비',
    detail: 'QA_REVIEWED 상태를 확인하고 다음 승인 단계를 엽니다.',
  });
  if (!businessReady) {
    throw new Error('QA 검토 후 업무 승인 양식을 찾지 못했습니다.');
  }
  const businessForm = businessApproveButton.locator('xpath=ancestor::div[@data-testid="stForm"][1]');
  await recordingFill(page, businessForm.locator('input').first(), '업무 승인자', reviewer, 1000);
  await recordingFill(
    page,
    businessForm.locator('textarea').first(),
    '업무 승인 의견',
    '개선안의 적용 범위, KPI, 단계 배포와 롤백 기준을 확인하여 업무 적용을 승인합니다.',
    1200
  );
  await recordingClick(
    page,
    businessApproveButton,
    '업무 승인 결과 저장',
    1900
  );
  await page.waitForTimeout(2800);
  await safePointAt(page, page.getByText('정식 승인 완료', { exact: true }).first(), 'BUSINESS_APPROVED · 정식 승인 완료', 3200);
  await page.waitForTimeout(2500);
  await showDemoFinale(page, { finalState: 'BUSINESS_APPROVED', holdMs: 15000 });
  await runIntegrationShowcase(page, { returnToVocDashboard: false, performAwsUpload: true });
  await showDemoStep(
    page,
    '부가기능 시연 완료',
    '본 시연 종료 후 Jira · GitHub · AWS 연동 기능을 짧게 확인했습니다.'
  );
  await page.waitForTimeout(7000);
}

(async () => {
  const browser = await chromium.launch({
    headless: false,
    args: ['--start-maximized'],
  });
  const context = await browser.newContext({ viewport: null });
  const page = await context.newPage();
  let lastCommandId = 0;
  let busy = false;

  await page.goto('http://localhost:8501');
  await page.waitForTimeout(3000);
  await ensureDemoCursor(page);
  writeStatus({ state: 'ready', commandId: lastCommandId, url: page.url() });

  const timer = setInterval(async () => {
    if (busy || !fs.existsSync(commandPath)) return;
    let command;
    try {
      command = JSON.parse(fs.readFileSync(commandPath, 'utf8'));
    } catch {
      return;
    }
    if (!command.id || command.id <= lastCommandId) return;

    busy = true;
    try {
      writeStatus({ state: 'running', commandId: command.id, action: command.action });
      if (command.action === 'full_recording_demo') {
        await runFullRecordingDemo(page);
      } else if (command.action === 'full_approval_rehearsal') {
        const identifiers = await runFullRecordingDemo(page, { continueToApproval: true });
        await runApprovalRecordingDemo(page, {
          ...command,
          ...identifiers,
          skipWarmup: true,
        });
      } else if (command.action === 'approval_recording_demo') {
        await runApprovalRecordingDemo(page, command);
      } else if (command.action === 'prewarm_recording_pages') {
        const timings = await warmupRecordingPages(page);
        writeStatus({
          state: 'completed',
          commandId: command.id,
          action: command.action,
          timings,
          url: page.url(),
        });
        lastCommandId = command.id;
        busy = false;
        return;
      } else if (command.action === 'integration_rehearsal_demo') {
        await runIntegrationShowcase(page);
        await showDemoStep(
          page,
          '연동 소개 리허설 완료',
          '조회 화면만 사용했으며 Jira 등록, GitHub Push, S3 업로드 데이터는 변경하지 않았습니다.'
        );
        await page.waitForTimeout(command.holdMs || 7000);
      } else if (command.action === 'rubric_agent_rehearsal') {
        await recordingClick(page, page.getByText('VOC 품질진단', { exact: true }), 'VOC 품질진단', 1000);
        await recordingClick(page, page.getByText('Agent 관리', { exact: true }), 'Agent 관리', 1000);
        await waitForStreamlitReady(page, page.getByRole('checkbox', { name: 'Agent 프로세스 상태 변경' }));
        await ensureAllAgentsRunning(page);
        await recordingClick(page, page.getByText('품질 평가 기준', { exact: true }), '품질 평가 기준', 1000);
        await waitForStreamlitReady(
          page,
          page.locator('div[class*="st-key-rubric_edit_internal_pipeline_widget_item_table"]')
        );
        await showRubricDetailDialog(page, 'internal_pipeline', '내부 Pipeline 품질');
        await selectRubricStage(page, 1, 'independent_judge', '독립 LLM Judge');
        await showRubricDetailDialog(page, 'independent_judge', '독립 LLM Judge');
        await selectRubricStage(page, 2, 'improvement_validity', '개선안 타당성');
        await showRubricDetailDialog(page, 'improvement_validity', '개선안 타당성');
        await showDemoStep(
          page,
          '세부 배점·Agent 사전 점검 완료',
          '세 평가 단계의 세부 배점 팝업과 6/6 Agent RUNNING 상태를 확인했습니다.'
        );
        await page.waitForTimeout(command.holdMs || 5000);
      } else if (command.action === 'pipeline_smoke_rehearsal') {
        await recordingClick(page, page.getByText('VOC 품질진단', { exact: true }), 'VOC 품질진단', 900);
        await recordingClick(page, page.getByText('수동 TC 수행', { exact: true }), '수동 TC 수행', 900);
        await waitForStreamlitReady(
          page,
          page.locator('div[class*="st-key-goal_testcase_table_"]'),
          { timeoutMs: 30000 }
        );
        const runButton = page.locator('div[class*="st-key-goal_execute_"] button:not([disabled])').first();
        await recordingClick(page, runButton, 'TC-01 Agent Pipeline 실행', 1200);
        await page.waitForTimeout(1600);
        await recordingClick(page, page.getByText('수동 TC 수행', { exact: true }), '실시간 상태 화면 갱신', 700);
        const judgeButton = page.locator('div[class*="st-key-goal_judge_execute_"] button:not([disabled])').first();
        const completed = await waitForRecordingState(page, judgeButton, {
          timeoutMs: command.timeoutMs || 180000,
          title: 'Pipeline 복구 검증 중',
          detail: '6개 Agent와 A2A Trace가 완료되어 독립 Judge 실행 단계가 열리는지 확인합니다.',
        });
        if (!completed) {
          const bodyText = await page.locator('body').innerText();
          const pipelineError = bodyText.match(/(?:파이프라인|Pipeline)[^\n]{0,100}(?:실패|오류|ERROR)/i)?.[0];
          throw new Error(pipelineError || 'Pipeline 복구 검증이 제한 시간 안에 완료되지 않았습니다.');
        }
        const bodyText = await page.locator('body').innerText();
        const runId = (bodyText.match(/RUN-[0-9]{8}-[0-9]{6}-[0-9]{6}-[0-9a-f]{4}/i) || [''])[0];
        await showDemoStep(
          page,
          'Pipeline 복구 검증 완료',
          `${runId || '신규 Run'} · 6개 Agent 실행 완료 · 독립 Judge 실행 가능`
        );
        await page.waitForTimeout(command.holdMs || 3500);
      } else if (command.action === 'human_approval_rehearsal') {
        const runId = String(command.runId || '').trim();
        const caseId = String(command.caseId || 'TC-01').trim();
        const reviewer = String(command.reviewer || '시연 담당자').trim();
        if (!runId) throw new Error('human_approval_rehearsal에는 runId가 필요합니다.');
        await recordingClick(page, page.getByText('VOC 품질진단', { exact: true }), 'VOC 품질진단', 800);
        await recordingClick(page, page.getByText('개선안 타당성 검증', { exact: true }), '개선안 타당성 검증', 800);
        const queryInput = page.locator('div[class*="st-key-voc_validity_candidate_query"] input');
        await queryInput.waitFor({ state: 'visible', timeout: 30000 });
        await recordingFill(page, queryInput, '승인 대상 Run 검색', runId, 800);
        await queryInput.press('Enter');
        await page.waitForTimeout(1800);
        const qaApproveButton = page.getByRole('button', { name: /QA 승인 저장$/ }).first();
        const qaReady = await waitForRecordingState(page, qaApproveButton, {
          timeoutMs: 30000,
          title: 'QA 검토 준비',
          detail: '대상 Run을 불러와 QA 검토 양식을 기다립니다.',
        });
        if (!qaReady) throw new Error('QA 검토 양식을 찾지 못했습니다.');
        const qaForm = qaApproveButton.locator('xpath=ancestor::div[@data-testid="stForm"][1]');
        await recordingFill(page, qaForm.locator('input').first(), 'QA 검토자', reviewer, 700);
        await recordingFill(page, qaForm.locator('textarea').first(), 'QA 검토 의견', '독립성, 타당성, Run·Trace 증적을 확인하여 QA 승인합니다.', 800);
        await recordingClick(page, qaApproveButton, 'QA 승인 저장', 1000);
        const businessApproveButton = page.getByRole('button', { name: /업무 승인 저장$/ }).first();
        const businessReady = await waitForRecordingState(page, businessApproveButton, {
          timeoutMs: 30000,
          title: '업무 승인 준비',
          detail: 'QA 검토 저장 후 업무 승인 단계를 기다립니다.',
        });
        if (!businessReady) throw new Error('업무 승인 양식을 찾지 못했습니다.');
        const businessForm = businessApproveButton.locator('xpath=ancestor::div[@data-testid="stForm"][1]');
        await recordingFill(page, businessForm.locator('input').first(), '업무 승인자', reviewer, 700);
        await recordingFill(page, businessForm.locator('textarea').first(), '업무 승인 의견', '적용 범위, KPI, 단계 배포와 롤백 기준을 확인하여 승인합니다.', 800);
        await recordingClick(page, businessApproveButton, '업무 승인 저장', 1000);
        const approved = await waitForRecordingState(page, page.getByText('정식 승인 완료', { exact: true }).first(), {
          timeoutMs: 30000,
          title: '정식 승인 확인',
          detail: 'BUSINESS_APPROVED 감사 이력이 저장되는지 확인합니다.',
        });
        if (!approved) throw new Error('정식 승인 완료 상태를 확인하지 못했습니다.');
        await showDemoFinale(page, { finalState: 'BUSINESS_APPROVED', holdMs: 5000 });
      } else if (command.action === 'preview_recording_scenario') {
        await showScenarioOverview(page, command.holdMs || 18000);
        await showDemoStep(
          page,
          '미리보기 1/12 · Dashboard',
          '최종 녹화는 실행 환경, Agent, 최신 Run, 독립 Judge와 결함 현황을 짧게 설명하며 시작합니다.'
        );
        await pointAndClick(
          page,
          page.getByText('VOC 품질진단', { exact: true }),
          'VOC 품질진단'
        );
        await pointAndClick(
          page,
          page.getByText('Dashboard', { exact: true }),
          'Dashboard'
        );
        await page.waitForTimeout(1800);
        await safePointAt(
          page,
          page.locator('.vqd-status-row'),
          '환경 · Agent · Run · Judge · 결함',
          3500
        );
        await safePointAt(
          page,
          page.locator('.vqd-connection-panel'),
          'A2A 연결과 Trace 상태',
          3000
        );
        await showDemoStep(
          page,
          '새 시연 흐름 미리보기 완료',
          '현재는 실행과 승인 데이터를 변경하지 않았습니다. 기능 완료 후 12단계를 하나의 연속 녹화로 수행합니다.'
        );
      } else if (command.action === 'open_agent_management') {
        await showDemoStep(page, '시연 1/5 · Agent 관리', 'Provider 인증 상태와 Agent 실행 상태를 확인합니다.');
        await pointAndClick(
          page,
          page.getByText('VOC 품질진단', { exact: true }),
          'VOC 품질진단'
        );
        await pointAndClick(
          page,
          page.getByText('Agent 관리', { exact: true }),
          'Agent 관리'
        );
        await page.getByRole('button', { name: 'Gemini 인증 점검' }).waitFor();
      } else if (command.action === 'click_auth') {
        await showDemoStep(
          page,
          '시연 1/5 · Provider 인증 점검',
          `${command.provider} API 자격 증명과 모델 호출 가능 여부를 확인합니다.`
        );
        await pointAndClick(
          page,
          page.locator(`div[class*="st-key-check_agent_${command.provider}_credential"] button`),
          `${command.provider} 인증 점검`
        );
        await page.getByText('최근 처리 상태', { exact: true }).waitFor();
        await page.waitForTimeout(command.waitMs || 1500);
      } else if (command.action === 'open_manual_tc') {
        await showDemoStep(page, '시연 2/5 · 수동 TC 수행', '대표 Test Case의 Pipeline과 Trace를 확인합니다.');
        await pointAndClick(
          page,
          page.getByText('수동 TC 수행', { exact: true }),
          '수동 TC 수행'
        );
        await page.waitForTimeout(1400);
        await ensureDemoCursor(page);
        await showDemoStep(page, '시연 2/5 · Case 선택', '읽기 전용 목록의 선택 Case와 실행 조건을 확인합니다.');
      } else if (command.action === 'inspect_page') {
        const bodyText = await page.locator('body').innerText();
        const rubricTabs = await page
          .locator('div[class*="st-key-voc_quality_rubric_stage"] label')
          .evaluateAll((labels) => labels.map((label, index) => ({
            index,
            text: label.innerText,
            html: label.outerHTML.slice(0, 500),
          })))
          .catch(() => []);
        lastCommandId = command.id;
        writeStatus({
          state: 'completed',
          commandId: command.id,
          action: command.action,
          url: page.url(),
          bodyText: bodyText.slice(0, command.maxChars || 30000),
          rubricTabs,
        });
        busy = false;
        return;
      } else if (command.action === 'run_selected_pipeline') {
        await ensureDemoCursor(page);
        await showDemoStep(
          page,
          '시연 2/5 · Agent Pipeline 실행',
          '선택한 Case를 6개 Agent에 전달하고 실시간 처리 흐름을 추적합니다.'
        );
        const runButton = page
          .locator('div[class*="st-key-goal_execute_"] button:not([disabled])')
          .first();
        await pointAndClick(page, runButton, 'Agent Pipeline 실행');
        await page.waitForTimeout(1600);
        await ensureDemoCursor(page);
        await showDemoStep(
          page,
          '시연 2/5 · Pipeline 처리 중',
          'Interpreter → Retriever → Summarizer → Evaluator → Critic → Improver 순서를 확인합니다.'
        );
      } else if (command.action === 'run_selected_judge') {
        await ensureDemoCursor(page);
        await showDemoStep(
          page,
          '시연 3/5 · 독립 LLM Judge',
          '저장된 동일 개선안을 Anthropic 독립 모델로 평가합니다.'
        );
        const judgeButton = page
          .locator('div[class*="st-key-goal_judge_execute_"] button:not([disabled])')
          .first();
        await pointAndClick(page, judgeButton, '독립 LLM 평가 실행');
        await page.waitForTimeout(1600);
        await ensureDemoCursor(page);
        await showDemoStep(
          page,
          '시연 3/5 · Judge 평가 중',
          '정확성·근거성·충실성·구체성을 내부 Agent와 독립적으로 판정합니다.'
        );
      } else if (command.action === 'open_history') {
        await showDemoStep(
          page,
          '시연 4/5 · 수행 이력',
          'Run ID, 실행 시각, Case 결과, Trace와 적용 Rubric을 확인합니다.'
        );
        await pointAndClick(
          page,
          page.getByText('수행 이력', { exact: true }),
          '수행 이력'
        );
        await page.waitForTimeout(1600);
        await ensureDemoCursor(page);
        await showDemoStep(
          page,
          '시연 4/5 · 최근 Run 확인',
          '방금 실행한 Run과 과거 실패 증적을 이력에서 비교할 수 있습니다.'
        );
      } else if (command.action === 'open_report') {
        await showDemoStep(
          page,
          '시연 5/5 · 품질 보고서',
          '정량 결과, 결함, 잔여 위험과 배포 판정 증적을 확인합니다.'
        );
        await pointAndClick(
          page,
          page.getByText('품질 보고서', { exact: true }),
          '품질 보고서'
        );
        await page.waitForTimeout(1800);
        await ensureDemoCursor(page);
        await showDemoStep(
          page,
          '시연 5/5 · 보고서 확인',
          'Run 이력과 연결된 품질 증적 및 최종 판정 자료입니다.'
        );
      } else if (command.action === 'open_acceptance') {
        await showDemoStep(
          page,
          '최종 확인 · 인수 및 시연',
          '기능·품질·증적 조건과 최종 인수 가능 여부를 확인합니다.'
        );
        await pointAndClick(
          page,
          page.getByText('최종 인수·시연', { exact: true }),
          '최종 인수·시연'
        );
        await page.waitForTimeout(1800);
        await ensureDemoCursor(page);
        await showDemoStep(
          page,
          '최종 확인 · 승인 조건',
          '실행 성공과 품질 승인을 분리하고 미충족 조건을 확인합니다.'
        );
      } else if (command.action === 'generate_acceptance_evidence') {
        await ensureDemoCursor(page);
        await showDemoStep(
          page,
          '최종 확인 · 인수 증적 생성',
          '현재 HOLD 판정과 미충족 Gate를 JSON·Markdown 증적으로 저장합니다.'
        );
        const evidenceButton = page
          .locator('div[class*="st-key-generate_voc_acceptance_"] button:not([disabled])')
          .first();
        await pointAndClick(page, evidenceButton, 'Step 10 인수 증적 생성');
        await page.waitForTimeout(1600);
        await ensureDemoCursor(page);
        await showDemoStep(
          page,
          '시연 완료 · HOLD 증적 저장',
          '미충족 조건을 숨기지 않고 현재 판정 그대로 인수 증적을 생성했습니다.'
        );
      } else if (command.action === 'show_step') {
        await ensureDemoCursor(page);
        await showDemoStep(page, command.title || 'VOC 품질진단 시연', command.detail || '');
      } else if (command.action === 'preview_finale') {
        await showDemoFinale(page, {
          finalState: command.finalState || 'BUSINESS_APPROVED',
          holdMs: command.holdMs || 15000,
        });
      } else if (command.action === 'close') {
        clearInterval(timer);
        await browser.close();
        writeStatus({ state: 'closed', commandId: command.id });
        process.exit(0);
      } else {
        throw new Error(`Unknown action: ${command.action}`);
      }
      lastCommandId = command.id;
      writeStatus({
        state: 'completed',
        commandId: command.id,
        action: command.action,
        url: page.url(),
      });
    } catch (error) {
      lastCommandId = command.id;
      writeStatus({
        state: 'failed',
        commandId: command.id,
        action: command.action,
        error: String(error),
      });
    } finally {
      busy = false;
    }
  }, 500);
})();
