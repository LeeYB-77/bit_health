'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Home } from 'lucide-react';

export default function AdminLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const router = useRouter();
    const pathname = usePathname();
    const [authorized, setAuthorized] = useState(false);

    useEffect(() => {
        const token = localStorage.getItem('access_token');
        const role = localStorage.getItem('user_role');
        const isVillaAdmin = localStorage.getItem('is_villa_admin') === 'true';

        if (!token || (role !== 'admin' && !isVillaAdmin)) {
            router.push('/login');
            return;
        }

        // 별장만 위임 관리하는 담당자는 golf/users/smtp 등 다른 관리 영역의
        // API를 호출할 권한이 없다. 대시보드 대신 비트별장 관리 화면으로 보낸다.
        if (role !== 'admin' && isVillaAdmin && pathname !== '/admin/villa') {
            router.replace('/admin/villa');
            return;
        }

        setAuthorized(true);
    }, [router, pathname]);

    if (!authorized) {
        return (
            <div className="flex min-h-screen items-center justify-center">
                <p className="text-gray-500">Checking authorization...</p>
            </div>
        );
    }

    return (
        <div className="flex min-h-screen flex-col bg-gray-50">
            <header className="bg-white shadow">
                <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 flex justify-between items-center">
                    <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                        관리자 대시보드
                    </h1>
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => router.push('/')}
                            className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800 font-medium transition-colors"
                        >
                            <Home size={16} />
                            사용자 페이지
                        </button>
                        <button
                            onClick={() => {
                                localStorage.clear();
                                router.push('/login');
                            }}
                            className="text-sm text-red-600 hover:text-red-800"
                        >
                            로그아웃
                        </button>
                    </div>
                </div>
            </header>
            <main>
                <div className="mx-auto max-w-7xl py-6 sm:px-6 lg:px-8">
                    {children}
                </div>
            </main>
        </div>
    );
}
