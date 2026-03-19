'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { API_URL } from '@/lib/api';
import { ArrowLeft, Search, CheckCircle, AlertCircle, Shield, User as UserIcon } from 'lucide-react';

interface User {
  id: number;
  name: string;
  birth_date: string;
  department: string | null;
  role: string;
}

export default function AdminUsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

  // Search/Filter state
  const [searchTerm, setSearchTerm] = useState('');
  const [currentUserName, setCurrentUserName] = useState('');

  useEffect(() => {
    setCurrentUserName(localStorage.getItem('user_name') || '');
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_URL}/api/users/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to fetch users');
      setUsers(await res.json());
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateRole = async (id: number, newRole: string) => {
    if (!confirm(`이 사용자의 권한을 '${newRole === 'admin' ? '관리자' : '일반 사용자'}'로 변경하시겠습니까?`)) return;

    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_URL}/api/users/${id}/role`, {
        method: 'PUT',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ role: newRole })
      });
      
      if (!res.ok) throw new Error('권한 변경에 실패했습니다.');

      setMessage({ type: 'success', text: '사용자 권한이 성공적으로 변경되었습니다.' });
      fetchUsers(); // Refresh list
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    }
  };

  const filteredUsers = users.filter(user =>
    user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (user.department && user.department.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="min-h-screen bg-gray-50 font-sans text-gray-900">
      {/* Header */}
      <div className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/admin')}
              className="p-2 rounded-full hover:bg-gray-100 transition-colors text-gray-500"
            >
              <ArrowLeft size={20} />
            </button>
            <h1 className="text-xl font-bold text-gray-800">관리자 등록 설정</h1>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        
        <div className="mb-6 p-4 rounded-xl bg-blue-50 border border-blue-100 text-blue-800 text-sm">
          <p>BIT SSO를 통해 가입된 회원들의 시스템 관리자 권한 여부를 설정할 수 있습니다. <strong>관리자</strong> 권한을 받은 사용자는 이 대시보드에 접근할 수 있게 됩니다.</p>
        </div>

        {/* Feedback Message */}
        {message && (
          <div className={`mb-6 p-4 rounded-lg flex items-center gap-3 shadow-sm ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
            }`}>
            {message.type === 'success' ? <CheckCircle size={20} /> : <AlertCircle size={20} />}
            <p className="text-sm font-medium">{message.text}</p>
            <button onClick={() => setMessage(null)} className="ml-auto text-sm hover:underline">닫기</button>
          </div>
        )}

        {/* Content Area */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden min-h-[500px]">

          <div className="p-6">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-lg font-bold text-gray-800">등록된 사용자 ({users.length})</h2>
              <div className="relative w-64">
                <input
                  type="text"
                  placeholder="이름 또는 부서 검색..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                />
                <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
              </div>
            </div>

            {loading ? (
              <div className="flex justify-center items-center h-64 text-gray-400">Loading...</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">이름</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">부서</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">현재 권한 상태</th>
                      <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">권한 설정</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {filteredUsers.length > 0 ? (
                      filteredUsers.map((user) => (
                        <tr key={user.id} className="hover:bg-gray-50 transition-colors">
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{user.name}</td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {user.department ? (
                              <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">
                                {user.department}
                              </span>
                            ) : '-'}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            <span className={`px-2 py-1 inline-flex text-xs leading-5 font-bold rounded-lg items-center gap-1 ${user.role === 'admin' ? 'bg-purple-100 text-purple-800' : 'bg-gray-100 text-gray-700'
                              }`}>
                              {user.role === 'admin' ? <Shield size={14}/> : <UserIcon size={14}/>}
                              {user.role === 'admin' ? '관리자' : '비관리자 (일반)'}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                            {user.role === 'admin' ? (
                              <button
                                onClick={() => handleUpdateRole(user.id, 'user')}
                                disabled={user.name === currentUserName}
                                className={`px-3 py-1.5 rounded-md transition-colors text-xs font-medium ${user.name === currentUserName ? 'bg-gray-50 text-gray-300 cursor-not-allowed' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                                title={user.name === currentUserName ? "본인 계정의 권한은 변경할 수 없습니다." : ""}
                              >
                                {user.name === currentUserName ? '내 계정 (강등 불가)' : '일반 사용자로 강등'}
                              </button>
                            ) : (
                              <button
                                onClick={() => handleUpdateRole(user.id, 'admin')}
                                className="px-3 py-1.5 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-md hover:bg-indigo-100 transition-colors text-xs font-semibold"
                              >
                                관리자 권한 부여
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={4} className="px-6 py-12 text-center text-sm text-gray-500">
                          검색 결과가 없습니다.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          
        </div>
      </div>
    </div>
  );
}
