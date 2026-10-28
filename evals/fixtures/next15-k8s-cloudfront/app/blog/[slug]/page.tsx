export const revalidate = 3600
export default async function Post({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const res = await fetch(`https://cdn.contentful.com/spaces/x/entries?fields.slug=${slug}`, { next: { tags: ['posts'] } })
  const data = await res.json()
  return <article>{data.items?.[0]?.fields?.title}</article>
}
