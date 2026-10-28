import express from 'express'
const app = express()
app.get('/users/:id', async (req, res) => {
  const user = await loadUser(req.params.id)
  res.json({ id: user.id, name: user.name, avatarUrl: `https://cdn.example.com/avatars/${user.id}.jpg` })
})
app.put('/users/:id/avatar', async (req, res) => {
  await uploadToBucket(`avatars/${req.params.id}.jpg`, req) // same key, overwritten
  res.sendStatus(204)
})
async function loadUser(id) { return { id, name: 'x' } }
async function uploadToBucket() {}
app.listen(3000)
