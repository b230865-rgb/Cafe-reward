import express from 'express'
import cors from 'cors'
import bcrypt from 'bcryptjs'
import jwt from 'jsonwebtoken'
import Database from 'better-sqlite3'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const db = new Database(path.join(__dirname, 'cafe-pont.db'))
const app = express()
const PORT = 3001
const JWT_SECRET = process.env.JWT_SECRET || 'cafe-pont-local-secret'

app.use(cors())
app.use(express.json())
db.pragma('journal_mode = WAL')
db.exec(`
  CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT UNIQUE NOT NULL, points INTEGER NOT NULL DEFAULT 0, lifetime_spend_cents INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id), type TEXT NOT NULL CHECK(type IN ('purchase', 'redemption')), amount_cents INTEGER, points_delta INTEGER NOT NULL, reward_name TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
`)

const memberCount = db.prepare('SELECT COUNT(*) AS count FROM members').get().count
if (!memberCount) {
  const seed = db.prepare('INSERT INTO members (name, phone, points, lifetime_spend_cents) VALUES (?, ?, ?, ?)')
  const members = [
    ['Maya Chen', '415-555-0138', 2380, 238000], ['Theo Grant', '415-555-0172', 1240, 124000],
    ['Rina Patel', '415-555-0191', 760, 76000], ['Jon Bell', '415-555-0114', 410, 41000],
    ['Ava Williams', '415-555-0155', 1840, 184000], ['Nico Santos', '415-555-0184', 320, 32000],
  ]
  const transaction = db.transaction(() => members.forEach((member) => seed.run(...member)))
  transaction()
}

function tierFor(member) {
  if (member.points >= 2000) return { name: 'Gold', multiplier: 2, next: null }
  if (member.points >= 500) return { name: 'Silver', multiplier: 1.5, next: 2000 }
  return { name: 'Regular', multiplier: 1, next: 500 }
}
function publicMember(member) {
  return { ...member, tier: tierFor(member), balance: member.points / 100 }
}
function auth(req, res, next) {
  const token = req.headers.authorization?.replace('Bearer ', '')
  try { req.user = jwt.verify(token, JWT_SECRET); next() } catch { res.status(401).json({ error: 'Please log in to continue.' }) }
}
function getMember(id) { return db.prepare('SELECT * FROM members WHERE id = ?').get(id) }

app.post('/api/auth/register', async (req, res) => {
  const { email, password } = req.body
  if (!email || !password || password.length < 6) return res.status(400).json({ error: 'Email and a 6+ character password are required.' })
  try {
    const result = db.prepare('INSERT INTO users (email, password_hash) VALUES (?, ?)').run(email.toLowerCase(), await bcrypt.hash(password, 10))
    res.status(201).json({ token: jwt.sign({ id: result.lastInsertRowid, email }, JWT_SECRET), email })
  } catch { res.status(409).json({ error: 'That email is already registered.' }) }
})
app.post('/api/auth/login', async (req, res) => {
  const user = db.prepare('SELECT * FROM users WHERE email = ?').get(String(req.body.email || '').toLowerCase())
  if (!user || !(await bcrypt.compare(req.body.password || '', user.password_hash))) return res.status(401).json({ error: 'Invalid email or password.' })
  res.json({ token: jwt.sign({ id: user.id, email: user.email }, JWT_SECRET), email: user.email })
})
app.get('/api/members', auth, (req, res) => {
  const page = Math.max(1, Number(req.query.page) || 1)
  const limit = Math.min(50, Math.max(1, Number(req.query.limit) || 5))
  const search = String(req.query.search || '').trim()
  const sort = ['name', 'points', 'lifetime_spend_cents'].includes(req.query.sort) ? req.query.sort : 'points'
  const direction = req.query.direction === 'asc' ? 'ASC' : 'DESC'
  const where = search ? 'WHERE name LIKE @search OR phone LIKE @search' : ''
  const params = search ? { search: `%${search}%` } : {}
  const total = db.prepare(`SELECT COUNT(*) AS count FROM members ${where}`).get(params).count
  const rows = db.prepare(`SELECT * FROM members ${where} ORDER BY ${sort} ${direction} LIMIT @limit OFFSET @offset`).all({ ...params, limit, offset: (page - 1) * limit })
  res.json({ members: rows.map(publicMember), page, limit, total, pages: Math.max(1, Math.ceil(total / limit)) })
})
app.get('/api/members/:id', auth, (req, res) => {
  const member = getMember(req.params.id)
  if (!member) return res.status(404).json({ error: 'Member not found.' })
  res.json({ member: publicMember(member), transactions: db.prepare('SELECT * FROM transactions WHERE member_id = ? ORDER BY created_at DESC LIMIT 12').all(member.id) })
})
app.post('/api/members/:id/purchase', auth, (req, res) => {
  const member = getMember(req.params.id)
  const cents = Math.round(Number(req.body.amount) * 100)
  if (!member || !Number.isFinite(cents) || cents <= 0) return res.status(400).json({ error: 'Enter a valid purchase amount.' })
  const tier = tierFor(member)
  const points = Math.floor(cents / 100 * tier.multiplier)
  const operation = db.transaction(() => {
    db.prepare('UPDATE members SET points = points + ?, lifetime_spend_cents = lifetime_spend_cents + ? WHERE id = ?').run(points, cents, member.id)
    db.prepare('INSERT INTO transactions (member_id, type, amount_cents, points_delta) VALUES (?, \'purchase\', ?, ?)').run(member.id, cents, points)
  })
  operation()
  res.status(201).json({ member: publicMember(getMember(member.id)), pointsAdded: points })
})
app.post('/api/members/:id/redeem', auth, (req, res) => {
  const member = getMember(req.params.id)
  const points = Math.floor(Number(req.body.points))
  const rewardName = String(req.body.rewardName || 'Free drink').trim()
  if (!member || !Number.isInteger(points) || points <= 0 || points > member.points) return res.status(400).json({ error: 'Not enough points for this redemption.' })
  const operation = db.transaction(() => {
    db.prepare('UPDATE members SET points = points - ? WHERE id = ?').run(points, member.id)
    db.prepare('INSERT INTO transactions (member_id, type, points_delta, reward_name) VALUES (?, \'redemption\', ?, ?)').run(member.id, -points, rewardName)
  })
  operation()
  res.status(201).json({ member: publicMember(getMember(member.id)), pointsUsed: points })
})
app.get('/api/health', (_req, res) => res.json({ status: 'ok' }))
app.listen(PORT, () => console.log(`Café Pont API listening on http://localhost:${PORT}`))
