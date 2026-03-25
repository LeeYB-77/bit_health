export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://59.10.164.2:8002';

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_name: string;
  role: string;
}

export const fetcher = async (url: string, options: RequestInit = {}) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  const headers = {
    'Content-Type': 'application/json',
    ...(token && { Authorization: `Bearer ${token}` }),
    ...(options.headers || {}),
  } as HeadersInit;

  const response = await fetch(`${API_URL}${url}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
    throw new Error(error.detail || response.statusText);
  }

  return response.json();
}

export interface GymStatus {
  count: number;
  congestion: 'free' | 'normal' | 'busy' | 'low' | 'medium' | 'high';
  my_status: 'in' | 'out';
  capacity: number;
}

export const getGymStatus = async (): Promise<GymStatus> => {
  return fetcher('/api/gym/status');
};

export const accessGym = async () => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${API_URL}/api/gym/access`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  return res.json();
};

export interface GolfSettings {
  weekday_slots: { start: string; end: string }[];
  weekend_start: number;
  weekend_end: number;
}

export interface GolfSlot {
  time: string;
  end_time: string;
  available: boolean;
  type: 'weekday' | 'weekend';
  taken_by_priority: number | null;  // 1,2,3 또는 null
  taken_res_id: number | null;
  can_preempt: boolean;              // 3시간 전 조건 충족 여부
}

export interface Reservation {
  id: number;
  start_time: string;
  end_time: string;
  participant_count: number;
  companions: string | null;
  status: string;
  priority: number;  // 1: 최우선, 2: 우선, 3: 양보
}

export const getGolfSlots = async (date: string): Promise<GolfSlot[]> => {
  return fetcher(`/api/golf/slots?date=${date}`);
};

export const reserveGolf = async (data: { start_time: string, end_time: string, participant_count: number, companions: string | null, priority: number }) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${API_URL}/api/golf/reserve`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Reservation failed');
  }
  return res.json();
};

export const cancelGolfReservation = async (id: number) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${API_URL}/api/golf/cancel/${id}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Cancellation failed');
  }
  return res.json();
};

export async function accessGolf() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${API_URL}/api/golf/access`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  if (!res.ok) {
    throw new Error('Failed to access golf facility');
  }
  return res.json();
};

export const getMyReservations = async (): Promise<Reservation[]> => {
  return fetcher('/api/golf/my');
};

export interface UserDashboardStats {
  monthly_count: number;
  has_today_reservation: boolean;
}

export const getUserDashboard = async (): Promise<UserDashboardStats> => {
  return fetcher('/api/users/me/dashboard');
};
