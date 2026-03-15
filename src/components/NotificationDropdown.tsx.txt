import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Bell, MessageSquare, X, CheckCircle, XCircle, Clock } from "lucide-react";
import { supabase } from "@/lib/supabaseClient";
import { motion, AnimatePresence } from "framer-motion";

interface Notification {
  id: string;
  job_id?: string;
  from_user_id?: string;
  to_user_id?: string;
  sender_name?: string;
  body?: string;
  created_at: string;
  is_read: boolean;
  unread_count?: number;
  type: 'message' | 'job';
  job_title?: string;
}

interface NotificationDropdownProps {
  currentUserId: string;
  currentUserType: 'user' | 'provider';
  onOpenChat?: (jobId: string) => void;
}

const NotificationDropdown = ({ currentUserId, currentUserType, onOpenChat }: NotificationDropdownProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  // Fetch recent notifications
  useEffect(() => {
    if (!currentUserId) return;

    const fetchNotifications = async () => {
      try {
        const allNotifications: Notification[] = [];
        
        // Fetch unread messages for jobs this user is involved in
        // Get jobs where user is requester or assigned worker
        const { data: userJobs } = await supabase
          .from('jobs')
          .select('id, title')
          .or(`requester_id.eq.${currentUserId},assigned_worker_id.eq.${currentUserId}`);

        if (userJobs && userJobs.length > 0) {
          const jobIds = userJobs.map(job => job.id);
          
          // Get unread messages for these jobs
            const { data: messages } = await supabase
            .from('messages')
              .select(`
              *,
              from_user:users!from_user_id (
                name
              ),
              job:jobs!job_id (
                title
              )
              `)
            .in('job_id', jobIds)
              .eq('is_read', false)
            .neq('from_user_id', currentUserId)
              .order('created_at', { ascending: false })
            .limit(10);

            if (messages) {
            // Group messages by job_id
              const groupedMessages = messages.reduce((acc, message) => {
              const jobId = message.job_id;
              if (!acc[jobId]) {
                acc[jobId] = [];
                }
              acc[jobId].push(message);
                return acc;
              }, {} as Record<string, any[]>);

            // Create one notification per job
            const messageNotifications = Object.entries(groupedMessages).map(([jobId, jobMessages]) => {
              const latestMessage = jobMessages[0];
              const job = userJobs.find(j => j.id === jobId);
                  
                  return {
                id: `message-${jobId}-${latestMessage.id}`,
                job_id: jobId,
                from_user_id: latestMessage.from_user_id,
                sender_name: latestMessage.from_user?.name || 'Unknown',
                body: latestMessage.body,
                    created_at: latestMessage.created_at,
                    is_read: false,
                unread_count: jobMessages.length,
                type: 'message' as const,
                job_title: job?.title || latestMessage.job?.title
              };
            });

            allNotifications.push(...messageNotifications);
          }
        }

        // Sort all notifications by created_at (newest first)
        allNotifications.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

        setNotifications(allNotifications);
        setUnreadCount(allNotifications.filter(n => !n.is_read).length);
      } catch (error) {
        // Silently fail - notifications are not critical
      }
    };

    fetchNotifications();
  }, [currentUserId, currentUserType]);

  // Real-time subscription for new messages
  useEffect(() => {
    if (!currentUserId) return;

    const subscription = supabase
      .channel(`notifications_${currentUserId}`)
      .on('postgres_changes', 
        { 
          event: 'INSERT', 
          schema: 'public', 
          table: 'messages',
          filter: `to_user_id=eq.${currentUserId}`
        },
        async (payload) => {
          const newMessage = payload.new as any;
          
          // Get sender name and job title
          const [senderResult, jobResult] = await Promise.all([
            supabase.from('users').select('name').eq('id', newMessage.from_user_id).single(),
            supabase.from('jobs').select('title').eq('id', newMessage.job_id).single()
          ]);

          const senderName = senderResult.data?.name || 'Unknown';
          const jobTitle = jobResult.data?.title || 'Job';

          // Check if we already have a notification for this job
              setNotifications(prev => {
            const existingNotificationIndex = prev.findIndex(n => n.job_id === newMessage.job_id);
                
                if (existingNotificationIndex !== -1) {
              // Update existing notification
                  const updatedNotifications = [...prev];
                  updatedNotifications[existingNotificationIndex] = {
                    ...updatedNotifications[existingNotificationIndex],
                body: newMessage.body,
                    created_at: newMessage.created_at,
                    unread_count: (updatedNotifications[existingNotificationIndex].unread_count || 0) + 1,
                is_read: false
                  };
                  return updatedNotifications;
                } else {
              // Create new notification
                  const newNotification: Notification = {
                id: `message-${newMessage.job_id}-${newMessage.id}`,
                job_id: newMessage.job_id,
                from_user_id: newMessage.from_user_id,
                    sender_name: senderName,
                body: newMessage.body,
                    created_at: newMessage.created_at,
                    is_read: false,
                    unread_count: 1,
                type: 'message',
                job_title: jobTitle
              };
              return [newNotification, ...prev.slice(0, 9)];
            }
          });
          
            setUnreadCount(prev => prev + 1);
        }
      )
      .subscribe();

    return () => {
      subscription.unsubscribe();
    };
  }, [currentUserId]);

  const formatTime = (timestamp: string) => {
    const now = new Date();
    const messageTime = new Date(timestamp);
    const diffInMinutes = Math.floor((now.getTime() - messageTime.getTime()) / (1000 * 60));
    
    if (diffInMinutes < 1) return 'Just now';
    if (diffInMinutes < 60) return `${diffInMinutes}m ago`;
    if (diffInMinutes < 1440) return `${Math.floor(diffInMinutes / 60)}h ago`;
    return messageTime.toLocaleDateString();
  };

  const markAsRead = async (notificationId: string) => {
    try {
      const notification = notifications.find(n => n.id === notificationId);
      if (!notification || !notification.job_id) return;

      // Mark all unread messages for this job as read
      await supabase
        .from('messages')
          .update({ is_read: true })
        .eq('job_id', notification.job_id)
        .eq('to_user_id', currentUserId)
        .eq('is_read', false);
      
      setNotifications(prev => prev.filter(n => n.id !== notificationId));
      setUnreadCount(prev => Math.max(0, prev - 1));
      
      window.dispatchEvent(new CustomEvent('notifications-updated', {
        detail: { userId: currentUserId, userType: currentUserType }
      }));
    } catch (error) {
      // Silently fail
    }
  };

  const markAllAsRead = async () => {
    if (notifications.length === 0) return;
    
    try {
      const jobIds = notifications
        .filter(n => n.job_id)
        .map(n => n.job_id!);
      
      if (jobIds.length > 0) {
        await supabase
          .from('messages')
          .update({ is_read: true })
          .in('job_id', jobIds)
          .eq('to_user_id', currentUserId)
          .eq('is_read', false);
      }
      
      setNotifications([]);
      setUnreadCount(0);
      
      window.dispatchEvent(new CustomEvent('notifications-updated', {
        detail: { userId: currentUserId, userType: currentUserType }
      }));
    } catch (error) {
      // Silently fail
    }
  };

  const handleNotificationClick = (notification: Notification) => {
    if (notification.type === 'message' && onOpenChat && notification.job_id) {
      markAsRead(notification.id);
      onOpenChat(notification.job_id);
      setIsOpen(false);
    } else {
      markAsRead(notification.id);
      setIsOpen(false);
    }
  };

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsOpen(!isOpen)}
        className="relative"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <Badge className="absolute -top-1 -right-1 h-5 w-5 rounded-full p-0 flex items-center justify-center text-xs bg-red-500 text-white border-2 border-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </Badge>
        )}
      </Button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            className="absolute right-0 top-full mt-2 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-50"
          >
            <div className="p-4 border-b">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">Notifications</h3>
                <div className="flex items-center gap-2">
                  {notifications.length > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={markAllAsRead}
                      className="text-xs"
                    >
                      Mark All Read
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setIsOpen(false)}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </div>

            <div className="max-h-96 overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="p-4 text-center text-muted-foreground">
                  <MessageSquare className="w-8 h-8 mx-auto mb-2 text-gray-400" />
                  <p>No new messages</p>
                </div>
              ) : (
                notifications.map((notification) => (
                  <motion.div
                    key={notification.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="p-4 border-b hover:bg-gray-50 cursor-pointer transition-colors"
                    onClick={() => handleNotificationClick(notification)}
                    title="Click to open chat"
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center">
                          <MessageSquare className="w-4 h-4 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <p className="font-medium text-sm truncate">
                              {notification.sender_name}
                            </p>
                            {notification.unread_count && notification.unread_count > 1 && (
                              <Badge variant="secondary" className="text-xs bg-primary/10 text-primary">
                                {notification.unread_count}
                              </Badge>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {formatTime(notification.created_at)}
                          </p>
                        </div>
                        {notification.job_title && (
                          <p className="text-xs text-muted-foreground mb-1">
                            {notification.job_title}
                          </p>
                        )}
                        <p className="text-sm text-muted-foreground truncate">
                          {notification.body}
                        </p>
                      </div>
                    </div>
                  </motion.div>
                ))
              )}
            </div>

            {notifications.length > 0 && (
              <div className="p-4 border-t">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={() => setIsOpen(false)}
                >
                  View All Messages
                </Button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default NotificationDropdown; 
