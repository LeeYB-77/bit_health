'use client';

import { useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { login } from '@/lib/auth';
import { Loader2, User, Lock, ArrowRight } from 'lucide-react';
import Image from 'next/image';

function LoginForm() {
  const [loading, setLoading] = useState(false);
  const searchParams = useSearchParams();
  const redirect = searchParams.get('redirect');

  const handleSSOLogin = () => {
    setLoading(true);
    if (redirect) {
      sessionStorage.setItem('postLoginRedirect', redirect);
    } else {
      sessionStorage.removeItem('postLoginRedirect');
    }
    const clientId = 'bit_health';
    const redirectUri = 'http://book.bit.kr/login/callback';
    const state = 'login_' + Math.random().toString(36).substring(7);
    const authUrl = `https://drive.bit.kr/auth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&response_type=code&scope=openid email profile&state=${state}`;
    window.location.href = authUrl;
  };

  return (
    <div className="w-full max-w-md bg-white border border-gray-100 rounded-3xl p-8 shadow-2xl animate-fade-in relative overflow-hidden">
      {/* Decorative elements */}
      <div className="absolute top-0 right-0 p-8 opacity-10 pointer-events-none">
        <div className="w-32 h-32 bg-blue-400 rounded-full blur-3xl transform translate-x-1/2 -translate-y-1/2"></div>
      </div>
      <div className="absolute bottom-0 left-0 p-8 opacity-10 pointer-events-none">
        <div className="w-32 h-32 bg-indigo-400 rounded-full blur-3xl transform -translate-x-1/2 translate-y-1/2"></div>
      </div>

      <div className="flex flex-col items-center mb-8 relative z-10">
        <div className="bg-white p-3 rounded-2xl shadow-lg mb-6">
          <Image src="/logo.svg" alt="BIT Wellness Center" width={140} height={40} className="w-auto h-10" />
        </div>
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">BIT Wellness Center</h1>
        <p className="text-blue-600 text-sm mt-1 opacity-80">Wellness Center 이용 관리 시스템</p>
      </div>

      <div className="space-y-6 relative z-10">
        <button
          onClick={handleSSOLogin}
          disabled={loading}
          className="w-full bg-blue-600 text-white font-bold py-3.5 rounded-xl hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-all shadow-lg active:scale-[0.98] flex items-center justify-center gap-2 group"
        >
          {loading ? (
            <Loader2 className="animate-spin" size={20} />
          ) : (
            <>
              BIT SSO 로그인 <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
            </>
          )}
        </button>
      </div>

      <div className="mt-8 text-center relative z-10">
        <p className="text-xs text-gray-400">
          문의: 관리팀 (내선 922)
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-white p-4 font-sans">
      <Suspense fallback={<div className="text-center">Loading...</div>}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
