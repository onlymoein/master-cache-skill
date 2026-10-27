import { Image } from 'expo-image'
import { useQuery } from '@tanstack/react-query'

export function Profile({ userId }: { userId: string }) {
  const { data: user } = useQuery({
    queryKey: ['user', userId],
    queryFn: () => fetch(`https://api.example.com/users/${userId}`).then((r) => r.json()),
    staleTime: Infinity,
  })
  // avatarUrl is https://cdn.example.com/avatars/<userId>.jpg and is overwritten on upload
  return <Image source={{ uri: user?.avatarUrl }} cachePolicy="disk" style={{ width: 64, height: 64 }} />
}
