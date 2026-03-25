'use client';

import { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ssoLogin } from '@/lib/auth';
import { Loader2 } from 'lucide-react';
import Image from 'next/image';

function CallbackHandler() {
  const [error, setError] = useState('');
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');

    if (!code) {
      setError('인증 코드가 없습니다. 다시 로그인해 주세요.');
      
      // Navigate back after a delay
      setTimeout(() => router.push('/login'), 3000);
      return;
    }

    const processLogin = async () => {
      try {
        const redirectUri = 'https://book.bit.kr/login/callback';
        const data = await ssoLogin(code, redirectUri);
        
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('user_name', data.user_name);
        localStorage.setItem('user_role', data.role);
        
        if (data.is_new_user) {
          alert('사용자 등록 완료');
        }

        const postLoginRedirect = sessionStorage.getItem('postLoginRedirect');
        if (postLoginRedirect) {
          sessionStorage.removeItem('postLoginRedirect');
          router.push(postLoginRedirect);
        } else {
          router.push('/');
        }
      } catch (err: any) {
        setError(err.message || 'SSO 로그인 처리에 실패했습니다.');
        setTimeout(() => router.push('/login'), 3000);
      }
    };

    processLogin();
  }, [router, searchParams]);

  return (
    <div className="w-full max-w-md bg-white border border-gray-100 rounded-3xl p-8 shadow-2xl relative overflow-hidden text-center">
      <div className="flex flex-col items-center mb-6">
        <Image src="/logo.svg" alt="BIT Wellness Center" width={140} height={40} className="w-auto h-10 mb-6" />
        
        {error ? (
          <div className="text-red-500 font-medium my-4">
            {error}
            <p className="text-sm mt-2 text-gray-500">잠시 후 로그인 화면으로 이동합니다...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center space-y-4 my-8">
            <Loader2 className="animate-spin text-blue-600" size={48} />
            <p className="text-gray-600 font-medium mt-4">SSO 인증 처리 중입니다...</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function CallbackPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4 font-sans">
      <Suspense fallback={<div className="text-center"><Loader2 className="animate-spin inline-block mr-2" />Loading...</div>}>
        <CallbackHandler />
      </Suspense>
    </div>
  );
}
