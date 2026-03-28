// ── More popover ─────────────────────────────────────────
const moreBtn     = document.getElementById('more-btn');
const morePopover = document.getElementById('more-popover');
if (moreBtn && morePopover) {
  moreBtn.addEventListener('click', e => {
    e.stopPropagation();
    const open = !morePopover.hidden;
    morePopover.hidden = open;
    moreBtn.setAttribute('aria-expanded', String(!open));
  });
  document.addEventListener('click', () => { morePopover.hidden = true; });
  morePopover.addEventListener('click', e => e.stopPropagation());
}

// ── Search drawer ─────────────────────────────────────────
const searchToggle = document.getElementById('search-toggle');
const searchDrawer = document.getElementById('search-drawer');
if (searchToggle && searchDrawer) {
  searchToggle.addEventListener('click', e => {
    e.preventDefault();
    searchDrawer.classList.toggle('open');
    if (searchDrawer.classList.contains('open')) {
      searchDrawer.querySelector('input')?.focus();
    }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') searchDrawer.classList.remove('open');
  });
}

// ── Like toggle ──────────────────────────────────────────
document.addEventListener('click', async e => {
  const btn = e.target.closest('.like-btn');
  if (!btn) return;
  const pid = btn.dataset.pid;
  const res = await fetch(`/like/${pid}`, { method: 'POST' });
  const data = await res.json();
  const svg = btn.querySelector('svg');
  if (data.liked) {
    btn.classList.add('liked');
    svg.setAttribute('fill', 'currentColor');
    svg.setAttribute('stroke', 'none');
    btn.setAttribute('aria-label', 'Unlike post');
  } else {
    btn.classList.remove('liked');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    btn.setAttribute('aria-label', 'Like post');
  }
  const likesEl = document.getElementById(`likes-${pid}`);
  if (likesEl) {
    likesEl.textContent = data.count + (data.count === 1 ? ' like' : ' likes');
    likesEl.style.transform = 'scale(1.1)';
    setTimeout(() => likesEl.style.transform = '', 200);
  }
});

// ── Comment toggle ───────────────────────────────────────
document.addEventListener('click', e => {
  const btn = e.target.closest('.comment-toggle');
  if (!btn) return;
  const pid = btn.dataset.pid;
  const box = document.getElementById(`cbox-${pid}`);
  if (box) {
    box.hidden = !box.hidden;
    if (!box.hidden) box.querySelector('.comment-input').focus();
  }
});

// ── Submit comment ───────────────────────────────────────
document.addEventListener('click', async e => {
  const btn = e.target.closest('.comment-submit');
  if (!btn) return;
  const pid = btn.dataset.pid;
  const box = document.getElementById(`cbox-${pid}`);
  const input = box.querySelector('.comment-input');
  const body = input.value.trim();
  if (!body) return;
  const res = await fetch(`/comment/${pid}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body })
  });
  const data = await res.json();
  if (data.error) return;
  const info = document.querySelector(`#post-${pid} .post-info`);
  const commentEl = document.createElement('div');
  commentEl.className = 'comment';
  commentEl.innerHTML = `<span class="username">${data.username}</span> ${data.body}`;
  box.before(commentEl);
  input.value = '';
});

// ── Follow / Unfollow ────────────────────────────────────
document.addEventListener('click', async e => {
  const btn = e.target.closest('[data-uid]');
  if (!btn || (!btn.classList.contains('follow-btn') && !btn.classList.contains('follow-btn-lg'))) return;
  const uid = btn.dataset.uid;
  const isFollowing = btn.dataset.following === 'true';
  const url = isFollowing ? `/unfollow/${uid}` : `/follow/${uid}`;
  const res = await fetch(url, { method: 'POST' });
  const data = await res.json();
  if (data.error) return;
  const nowFollowing = data.status === 'following';
  btn.dataset.following = nowFollowing ? 'true' : 'false';
  btn.textContent = nowFollowing ? 'Following' : 'Follow';
  if (btn.classList.contains('follow-btn-lg')) {
    btn.classList.toggle('following', nowFollowing);
  }
  // Update follower count on profile page if present
  const fc = document.getElementById(`fc-${uid}`);
  if (fc) fc.textContent = data.followers;
});

// ── Delete post ──────────────────────────────────────────
document.addEventListener('click', async e => {
  const btn = e.target.closest('.delete-btn');
  if (!btn) return;
  if (!confirm('Delete this post?')) return;
  const pid = btn.dataset.pid;
  const res = await fetch(`/post/${pid}/delete`, { method: 'POST' });
  const data = await res.json();
  if (data.status === 'deleted') {
    const postEl = document.getElementById(`post-${pid}`);
    if (postEl) postEl.remove();
  }
});
