'use client';

import { useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { login } from '@/lib/auth';
import { Loader2, User, Lock, ArrowRight } from 'lucide-react';
import Image from 'next/image';

function LoginForm() {
  const [name, setName] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectUrl = searchParams.get('redirect');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const data = await login(name, birthDate);
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('user_name', data.user_name);
      localStorage.setItem('user_role', data.role);

      if (redirectUrl) {
        router.push(redirectUrl);
      } else if (data.role === 'admin') {
        router.push('/admin');
      } else {
        router.push('/');
      }
    } catch (err: any) {
      setError(err.message || '로그인에 실패했습니다.');
    } finally {
      setLoading(false);
    }
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
          <Image src="/logo.svg" alt="BIT Health" width={140} height={40} className="w-auto h-10" />
        </div>
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">BIT Health</h1>
        <p className="text-blue-600 text-sm mt-1 opacity-80">임직원 건강 관리 시스템</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6 relative z-10">
        {error && (
          <div className="bg-red-500/20 border border-red-500/30 text-red-100 text-sm p-3 rounded-xl flex items-center justify-center backdrop-blur-sm">
            {error}
          </div>
        )}

        <div className="space-y-4">
          <div className="relative group">
            <User className="absolute left-4 top-3.5 h-5 w-5 text-gray-400 group-focus-within:text-blue-600 transition-colors" />
            <input
              type="text"
              placeholder="이름"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-gray-50 border border-gray-200 text-gray-900 placeholder-gray-400 rounded-xl py-3 pl-12 pr-4 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all font-medium"
              required
            />
          </div>

          <div className="relative group">
            <Lock className="absolute left-4 top-3.5 h-5 w-5 text-gray-400 group-focus-within:text-blue-600 transition-colors" />
            <input
              type="password"
              placeholder="비밀번호 (생년월일 6자리: 예 801010)"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
              className="w-full bg-gray-50 border border-gray-200 text-gray-900 placeholder-gray-400 rounded-xl py-3 pl-12 pr-4 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all font-medium"
              required
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 text-white font-bold py-3.5 rounded-xl hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-all shadow-lg active:scale-[0.98] flex items-center justify-center gap-2 group"
        >
          {loading ? (
            <Loader2 className="animate-spin" size={20} />
          ) : (
            <>
              로그인 <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
            </>
          )}
        </button>
      </form>

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
