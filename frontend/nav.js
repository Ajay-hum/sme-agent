// Shared navigation bar — injected into every authenticated page.
// Include this script and call renderOgaNav('current-page-id') after <body> loads.

function renderOgaNav(activePage) {
  const token        = localStorage.getItem('oga_token');
  const businessName = localStorage.getItem('oga_business_name') || '';

  if (!token) {
    window.location.href = '/login';
    return;
  }

  const pages = [
    { id: 'chat',  label: '⚡ Chat',      url: '/'      },
    { id: 'pos',   label: '🛒 Quick Sale', url: '/pos'   },
    { id: 'admin', label: '📦 Products',   url: '/admin' },
  ];

  const navHtml = `
    <div id="oga-nav" style="
      background:#1a1a2e; color:#fff; padding:0 24px; height:48px;
      display:flex; align-items:center; gap:4px;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
      flex-shrink:0;
    ">
      <span style="font-size:16px; font-weight:700; color:#e8b84b; letter-spacing:-0.5px; margin-right:18px;">
        Oga
      </span>
      ${pages.map(p => `
        <a href="${p.url}" style="
          padding:7px 14px; border-radius:7px; font-size:12.5px;
          text-decoration:none; color:${p.id === activePage ? '#1a1a2e' : 'rgba(255,255,255,0.75)'};
          background:${p.id === activePage ? '#e8b84b' : 'transparent'};
          font-weight:${p.id === activePage ? '600' : '500'};
          transition:background 0.15s;
        ">${p.label}</a>
      `).join('')}
      <span style="margin-left:auto; font-size:11.5px; color:rgba(255,255,255,0.55);">
        ${esc(businessName)}
      </span>
      <button onclick="ogaLogout()" style="
        margin-left:14px; padding:6px 12px; border-radius:7px;
        border:none; background:rgba(255,90,90,0.18); color:#ff8a8a;
        font-size:12px; cursor:pointer; font-family:inherit;
      ">Log out</button>
    </div>
  `;

  document.body.insertAdjacentHTML('afterbegin', navHtml);
}

function ogaLogout() {
  localStorage.removeItem('oga_token');
  localStorage.removeItem('oga_user_id');
  localStorage.removeItem('oga_business_id');
  localStorage.removeItem('oga_business_name');
  localStorage.removeItem('oga_full_name');
  window.location.href = '/login';
}

function esc(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}