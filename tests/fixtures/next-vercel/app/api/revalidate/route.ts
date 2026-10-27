export async function GET() {
  return new Response('ok', { headers: { 'Cache-Control': 'public, max-age=60', 'Vary': 'Cookie' } })
}
