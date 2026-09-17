import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type Member = { id: number; name: string; phone: string; points: number; balance: number; lifetime_spend_cents: number; tier: { name: string; multiplier: number; next: number | null } }
type Transaction = { id: number; type: string; points_delta: number; amount_cents?: number; reward_name?: string; created_at: string }

const api = async (path: string, options: RequestInit = {}, token = '') => {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || 'Something went wrong.')
  return data
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('cafe-token') || '')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [register, setRegister] = useState(false)
  const [members, setMembers] = useState<Member[]>([])
  const [selected, setSelected] = useState<Member | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('points')
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [purchaseAmount, setPurchaseAmount] = useState('')
  const [redeemPoints, setRedeemPoints] = useState('500')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  async function loadMembers() {
    if (!token) return
    try {
      const data = await api(`/api/members?search=${encodeURIComponent(search)}&sort=${sort}&page=${page}&limit=5`, {}, token)
      setMembers(data.members); setPages(data.pages)
      if (selected) {
        const current = data.members.find((member: Member) => member.id === selected.id)
        if (current) await selectMember(current)
      }
    } catch (reason) { setError((reason as Error).message) }
  }
  async function selectMember(member: Member) {
    const data = await api(`/api/members/${member.id}`, {}, token)
    setSelected(data.member); setTransactions(data.transactions)
  }
  useEffect(() => { loadMembers() }, [token, search, sort, page])

  async function submitAuth(event: FormEvent) {
    event.preventDefault(); setError('')
    try {
      const data = await api(register ? '/api/auth/register' : '/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
      localStorage.setItem('cafe-token', data.token); setToken(data.token)
    } catch (reason) { setError((reason as Error).message) }
  }
  async function runAction(type: 'purchase' | 'redeem') {
    if (!selected) return
    setError(''); setNotice('')
    const rawValue = type === 'purchase' ? purchaseAmount : redeemPoints
    const numericValue = Number(rawValue)
    if (!Number.isFinite(numericValue) || numericValue <= 0 || (type === 'redeem' && !Number.isInteger(numericValue))) {
      setError(type === 'purchase' ? 'Enter a purchase amount greater than zero.' : 'Enter whole points greater than zero.')
      return
    }
    try {
      const data = await api(`/api/members/${selected.id}/${type}`, { method: 'POST', body: JSON.stringify(type === 'purchase' ? { amount: purchaseAmount } : { points: redeemPoints, rewardName: 'Free drink' }) }, token)
      setSelected(data.member); setNotice(type === 'purchase' ? `Added ${data.pointsAdded} points.` : `Redeemed ${data.pointsUsed} points.`)
      setPurchaseAmount(''); await loadMembers(); await selectMember(data.member)
    } catch (reason) { setError((reason as Error).message) }
  }

  if (!token) return <main className="auth-shell"><section className="landing"><div className="brand">PONT / REWARDS</div><div className="landing-copy"><p className="eyebrow">THE COUNTER, IN PERFECT BALANCE</p><h1>Make every regular feel like a regular.</h1><p className="lead">A calm, precise rewards counter for independent cafes. Track visits, earn trust, and keep every point accounted for.</p><div className="feature-row"><span>01 <b>Live balances</b></span><span>02 <b>Tier-aware earning</b></span><span>03 <b>Fast member lookup</b></span></div></div></section><form className="auth-card" onSubmit={submitAuth}><p className="eyebrow">STAFF ACCESS</p><h2>{register ? 'Create your counter login' : 'Welcome back'}</h2><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={6} required /></label>{error && <p className="error">{error}</p>}<button className="primary" type="submit">{register ? 'Create account' : 'Open counter'} <span>-&gt;</span></button><button className="link-button" type="button" onClick={() => setRegister(!register)}>{register ? 'Already have an account? Sign in' : 'New here? Create a login'}</button></form></main>

  return <main className="app-shell"><header><div className="brand">PONT / REWARDS</div><div className="header-meta"><span className="status-dot" /> COUNTER ONLINE <button className="logout" onClick={() => { localStorage.removeItem('cafe-token'); setToken(''); setSelected(null) }}>Sign out</button></div></header><section className="dashboard-heading"><div><p className="eyebrow">TUESDAY, 17 SEPTEMBER 2026</p><h1>Good morning, operator.</h1><p className="muted">Choose a member to make the next moment count.</p></div><div className="next-features"><span>Built next:</span> member insights · rewards catalog · multi-location</div></section><section className="workspace"><aside className="member-panel"><div className="panel-top"><div><p className="eyebrow">MEMBERS</p><strong>{members.length} showing</strong></div><select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1) }}><option value="points">Most points</option><option value="name">Name A-Z</option><option value="lifetime_spend_cents">Lifetime spend</option></select></div><input className="search" placeholder="Search name or phone..." value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} /> <div className="member-list">{members.map((member) => <button className={`member-row ${selected?.id === member.id ? 'active' : ''}`} key={member.id} onClick={() => selectMember(member)}><span className="avatar">{member.name.split(' ').map((part) => part[0]).join('')}</span><span className="member-name"><b>{member.name}</b><small>{member.phone}</small></span><span className="member-points"><b>{member.points.toLocaleString()}</b><small>pts</small></span></button>)}{!members.length && <p className="empty">No members match that search.</p>}</div><div className="pagination"><button disabled={page === 1} onClick={() => setPage(page - 1)}>&lt;</button><span>Page {page} of {pages}</span><button disabled={page === pages} onClick={() => setPage(page + 1)}>&gt;</button></div></aside><section className="detail-panel">{selected ? <><div className="member-hero"><div><p className="eyebrow">MEMBER PROFILE</p><h2>{selected.name}</h2><p className="muted">{selected.phone}</p></div><span className={`tier tier-${selected.tier.name.toLowerCase()}`}>{selected.tier.name} · {selected.tier.multiplier}x earning</span></div><div className="balance-card"><div><span className="eyebrow">CURRENT BALANCE</span><strong>{selected.points.toLocaleString()} <small>points</small></strong><p className="muted">${selected.balance.toFixed(2)} in rewards value</p></div><div className="balance-mark">*</div></div><div className="actions"><div className="action-card"><p className="eyebrow">RECORD PURCHASE</p><h3>Turn a visit into points.</h3><div className="inline-form"><span>$</span><input type="number" min="0.01" step="0.01" placeholder="0.00" value={purchaseAmount} onChange={(event) => setPurchaseAmount(event.target.value)} /><button className="primary" onClick={() => runAction('purchase')}>Add points</button></div><small>Earns at {selected.tier.multiplier}x for {selected.tier.name} members.</small></div><div className="action-card redeem"><p className="eyebrow">REDEEM REWARD</p><h3>Give something back.</h3><div className="inline-form"><input type="number" min="1" step="1" value={redeemPoints} onChange={(event) => setRedeemPoints(event.target.value)} /><span>pts</span><button className="secondary" onClick={() => runAction('redeem')}>Redeem</button></div><small>Free drink redemption from 500 points.</small></div></div>{(notice || error) && <p className={error ? 'error toast' : 'success toast'}>{error || notice}</p>}<div className="history"><div className="history-heading"><p className="eyebrow">RECENT ACTIVITY</p><span>Audited ledger</span></div>{transactions.map((transaction) => <div className="transaction" key={transaction.id}><span className={`transaction-icon ${transaction.type}`}>{transaction.type === 'purchase' ? '+' : '-'}</span><span><b>{transaction.type === 'purchase' ? 'Purchase' : transaction.reward_name}</b><small>{new Date(transaction.created_at).toLocaleString()}</small></span><strong className={transaction.points_delta > 0 ? 'positive' : 'negative'}>{transaction.points_delta > 0 ? '+' : ''}{transaction.points_delta} pts</strong></div>)}</div></> : <div className="empty-state"><span>*</span><h2>Select a member</h2><p>Search by name or phone to start a precise reward moment.</p></div>}</section></section></main>
}

export default App
