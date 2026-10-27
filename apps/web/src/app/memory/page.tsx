import { redirect } from 'next/navigation';

export default function MemoryPageRedirect() {
  redirect('/?overlay=memory');
}
