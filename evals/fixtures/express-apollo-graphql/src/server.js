import express from 'express'
import cors from 'cors'
import { ApolloServer } from '@apollo/server'
import { expressMiddleware } from '@apollo/server/express4'
import DataLoader from 'dataloader'
import pg from 'pg'

const db = new pg.Pool()
// Shared across all requests
const authorLoader = new DataLoader(async (ids) => {
  const { rows } = await db.query('select * from authors where id = any($1)', [ids])
  return ids.map((id) => rows.find((r) => r.id === id))
})

const typeDefs = `#graphql
  type Author { id: ID!  name: String! }
  type Book { id: ID!  title: String!  author: Author!  price: Float! }
  type Query { books(category: String): [Book!]!  me: Author }
`
const resolvers = {
  Query: {
    books: async (_, { category }) => (await db.query('select * from books where category = $1', [category])).rows,
    me: async (_, __, ctx) => ctx.user,
  },
  Book: { author: (book) => authorLoader.load(book.author_id) },
}

const server = new ApolloServer({ typeDefs, resolvers })
await server.start()
const app = express()
app.use('/graphql', cors(), express.json(), expressMiddleware(server, { context: async ({ req }) => ({ user: req.headers.authorization ? { id: '1' } : null }) }))
app.listen(4000)
