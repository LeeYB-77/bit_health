'use client';

import { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { login } from '@/lib/auth';
import { Loader2, User, Lock, ArrowRight } from 'lucide-react';
import Image from 'next/image';

function LoginForm() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const searchParams = useSearchParams();
  const redirect = searchParams.get('redirect');

  // SSO의 redirect_uri는 https://book.bit.kr로 고정되어 있어(README 5) 로컬에서는
  // SSO 로그인이 운영으로 돌아간다. 그래서 localhost에서만 개발용 로그인을 노출한다.
  // 운영 도메인에서는 렌더링 자체가 되지 않는다.
  const [isLocalhost, setIsLocalhost] = useState(false);
  const [devName, setDevName] = useState('admin');
  const [devBirth, setDevBirth] = useState('000000');
  const [devLoading, setDevLoading] = useState(false);
  const [devError, setDevError] = useState('');

  useEffect(() => {
    const host = window.location.hostname;
    setIsLocalhost(host === 'localhost' || host === '127.0.0.1');
  }, []);

  const handleDevLogin = async () => {
    setDevLoading(true);
    setDevError('');
    try {
      const data = await login(devName.trim(), devBirth.trim());
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('user_name', data.user_name);
      localStorage.setItem('user_role', data.role);
      localStorage.setItem('is_villa_admin', String(data.is_villa_admin));
      router.push(redirect || '/');
    } catch (e) {
      setDevError(e instanceof Error ? e.message : '로그인에 실패했습니다.');
    } finally {
      setDevLoading(false);
    }
  };

  const handleSSOLogin = () => {
    setLoading(true);
    if (redirect) {
      sessionStorage.setItem('postLoginRedirect', redirect);
    } else {
      sessionStorage.removeItem('postLoginRedirect');
    }
    const clientId = 'bit_health';
    const redirectUri = 'https://book.bit.kr/login/callback';
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

      {isLocalhost && (
        <div className="mt-6 pt-6 border-t border-dashed border-gray-200 relative z-10">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
              로컬 개발 전용
            </span>
            <span className="text-xs text-gray-400">운영에서는 표시되지 않습니다</span>
          </div>
          <p className="text-xs text-gray-500 mb-3 leading-relaxed">
            SSO는 운영 도메인으로만 돌아오므로 로컬에서는 이름과 생년월일로 로그인합니다.
          </p>

          <div className="space-y-2">
            <div className="relative">
              <User size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={devName}
                onChange={(e) => setDevName(e.target.value)}
                placeholder="이름"
                className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-gray-200 bg-gray-50 text-sm outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="relative">
              <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={devBirth}
                onChange={(e) => setDevBirth(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleDevLogin(); }}
                placeholder="생년월일 6자리"
                className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-gray-200 bg-gray-50 text-sm outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {devError && <p className="text-xs text-rose-600">{devError}</p>}

            <button
              onClick={handleDevLogin}
              disabled={devLoading || !devName.trim() || !devBirth.trim()}
              className="w-full bg-gray-800 text-white font-bold py-2.5 rounded-xl text-sm hover:bg-gray-900 disabled:bg-gray-300 flex items-center justify-center gap-2"
            >
              {devLoading ? <Loader2 size={16} className="animate-spin" /> : '개발용 로그인'}
            </button>
          </div>

          <div className="mt-3 flex flex-wrap gap-1.5">
            {[
              { name: 'admin', birth: '000000', label: 'admin (관리자)' },
              { name: '김직원', birth: '900101', label: '김직원' },
              { name: '박사원', birth: '900102', label: '박사원' },
              { name: '이과장', birth: '900103', label: '이과장' },
            ].map((account) => (
              <button
                key={account.name}
                onClick={() => { setDevName(account.name); setDevBirth(account.birth); }}
                className="text-[11px] px-2 py-1 rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
              >
                {account.label}
              </button>
            ))}
          </div>
        </div>
      )}

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
