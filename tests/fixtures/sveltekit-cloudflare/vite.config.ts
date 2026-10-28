import { sveltekit } from '@sveltejs/kit/vite'
import adapter from '@sveltejs/adapter-cloudflare'
export default { plugins: [sveltekit({ adapter: adapter() })] }
