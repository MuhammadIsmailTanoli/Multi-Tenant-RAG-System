import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Cpu, ShieldCheck, User, Sparkles, AlertCircle, Gauge } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { ChatMessage, RateLimitErrorDetail } from '../types';
import { queryHandbook, RateLimitError } from '../utils/api';
import { MarkdownRenderer } from './MarkdownRenderer';

interface ChatPageProps {
  onRateLimitHit: (detail: RateLimitErrorDetail) => void;
  onOpenLimits?: () => void;
}

export const ChatPage: React.FC<ChatPageProps> = ({ onRateLimitHit, onOpenLimits }) => {
  const { activeTenant, tokens } = useTheme();
  const { session, googleUser, refreshLimitsStatus } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuery, setInputQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Initialize welcoming message on tenant load
  useEffect(() => {
    const welcomeText =
      activeTenant === 'acme'
        ? `Hello **${googleUser?.name || 'there'}**! Welcome to the **Acme Corporation** internal knowledge base.`
        : `Identity confirmed: **${googleUser?.email || 'Authorized User'}**. Connected to **Globex Corporation** Enterprise Policy Intelligence.`;

    setMessages([
      {
        id: 'welcome-msg',
        role: 'assistant',
        content: welcomeText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        tenantId: activeTenant as 'acme' | 'globex',
      },
    ]);
  }, [activeTenant, googleUser?.name, googleUser?.email]);

  // Auto-scroll to bottom of message list
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSendQuery = async (queryText?: string) => {
    const textToSend = (queryText || inputQuery).trim();
    if (!textToSend || isLoading || !session || !activeTenant) return;

    setInputQuery('');

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      tenantId: activeTenant,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const response = await queryHandbook(activeTenant, textToSend, session.accessToken);

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.answer,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        tenantId: activeTenant,
      };

      setMessages((prev) => [...prev, assistantMessage]);
      // Update limits counter in background after successful query
      refreshLimitsStatus();
    } catch (err: any) {
      if (err instanceof RateLimitError) {
        // Refresh limits so the counter shows the exhausted state, then trigger popup
        refreshLimitsStatus();
        onRateLimitHit(err.detail);
        return;
      }

      const errorMessage: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: `**Request Failed:** ${err.message || 'Unable to process query. Please check your connection and try again.'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        tenantId: activeTenant,
        isError: true,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendQuery();
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4.5rem)] sm:h-[calc(100vh-5rem)] max-w-5xl mx-auto px-3 sm:px-4 py-3 relative z-10">
      {/* Message Feed */}
      <div className="flex-1 overflow-y-auto pr-1 sm:pr-2 space-y-4 pt-4 sm:pt-6 pb-2">
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className={`flex items-start gap-2.5 sm:gap-3.5 ${
                msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'
              }`}
            >
              {/* Avatar */}
              <div
                className={`w-8 h-8 sm:w-9 sm:h-9 shrink-0 flex items-center justify-center text-xs shadow-md rounded-xl ${
                  msg.role === 'user'
                    ? 'bg-white/10 text-white border border-white/15'
                    : activeTenant === 'acme'
                      ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                      : 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30'
                }`}
              >
                {msg.role === 'user' ? (
                  googleUser?.picture ? (
                    <img
                      src={googleUser.picture}
                      alt="User"
                      className="w-full h-full rounded-xl object-cover"
                    />
                  ) : (
                    <User className="w-4 h-4" />
                  )
                ) : activeTenant === 'acme' ? (
                  <Cpu className="w-4 h-4" />
                ) : (
                  <ShieldCheck className="w-4 h-4" />
                )}
              </div>

              {/* Message Bubble */}
              <div
                className={`max-w-[85%] sm:max-w-[78%] p-4 sm:p-5 text-sm shadow-lg backdrop-blur-2xl ${
                  msg.role === 'user'
                    ? activeTenant === 'acme'
                      ? 'bg-amber-500/20 text-amber-100 rounded-2xl rounded-tr-none border border-amber-500/30 shadow-[0_4px_20px_rgba(245,158,11,0.1)]'
                      : 'bg-cyan-500/20 text-cyan-100 rounded-2xl rounded-tr-none border border-cyan-500/30 shadow-[0_4px_20px_rgba(6,182,212,0.1)]'
                    : msg.isError
                      ? 'bg-red-950/40 text-red-200 rounded-2xl rounded-tl-none border border-red-500/30'
                      : 'bg-white/[0.04] text-slate-200 rounded-2xl rounded-tl-none border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.4)]'
                }`}
              >
                {msg.role === 'assistant' ? (
                  <MarkdownRenderer content={msg.content} />
                ) : (
                  <div className="whitespace-pre-wrap font-medium">{msg.content}</div>
                )}
                <div
                  className={`mt-2 text-[10px] select-none flex items-center justify-end font-mono ${
                    msg.role === 'user' ? 'text-white/60' : 'text-slate-500'
                  }`}
                >
                  {msg.timestamp}
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Themed Thinking / Processing Indicator */}
        {isLoading && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start gap-3"
          >
            <div
              className={`w-8 h-8 sm:w-9 sm:h-9 shrink-0 flex items-center justify-center text-xs rounded-xl ${
                activeTenant === 'acme'
                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                  : 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30'
              }`}
            >
              <Sparkles className="w-4 h-4 animate-spin" />
            </div>

            <div className="p-4 rounded-2xl rounded-tl-none backdrop-blur-2xl bg-white/[0.04] border border-white/10 shadow-lg text-xs">
              <div className="flex items-center gap-2.5">
                <span className="text-slate-400 font-medium">
                  {activeTenant === 'acme'
                    ? 'Retrieving Acme handbook context...'
                    : 'Querying Globex classified vector index...'}
                </span>
                <div className="flex gap-1.5">
                  <motion.span
                    className={`w-1.5 h-1.5 rounded-full ${
                      activeTenant === 'acme' ? 'bg-amber-400' : 'bg-cyan-400'
                    }`}
                    animate={{ y: [0, -5, 0], opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 0.6, repeat: Infinity }}
                  />
                  <motion.span
                    className={`w-1.5 h-1.5 rounded-full ${
                      activeTenant === 'acme' ? 'bg-amber-400' : 'bg-cyan-400'
                    }`}
                    animate={{ y: [0, -5, 0], opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 0.6, repeat: Infinity, delay: 0.15 }}
                  />
                  <motion.span
                    className={`w-1.5 h-1.5 rounded-full ${
                      activeTenant === 'acme' ? 'bg-amber-400' : 'bg-cyan-400'
                    }`}
                    animate={{ y: [0, -5, 0], opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 0.6, repeat: Infinity, delay: 0.3 }}
                  />
                </div>
              </div>
            </div>
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Bottom Glass Input Bar */}
      <div className="p-2 sm:p-2.5 rounded-2xl backdrop-blur-2xl bg-white/[0.04] border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)] mt-2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendQuery();
          }}
          className="flex items-center gap-2 sm:gap-3"
        >
          {/* Usage Quota Button placed on side of chat box */}
          {onOpenLimits && (
            <button
              type="button"
              onClick={onOpenLimits}
              className={`p-2.5 sm:px-3 sm:py-2.5 text-xs font-semibold rounded-xl flex items-center gap-1.5 shrink-0 transition-all border ${
                activeTenant === 'acme'
                  ? 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border-amber-500/25'
                  : 'bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border-cyan-500/25'
              }`}
              title="Inspect Daily & Weekly Quotas / Usage"
            >
              <Gauge className="w-4 h-4" />
              <span className="hidden sm:inline">Usage</span>
            </button>
          )}

          <textarea
            value={inputQuery}
            onChange={(e) => {
              if (e.target.value.length <= 500) {
                setInputQuery(e.target.value);
              }
            }}
            maxLength={500}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={isLoading}
            placeholder={
              activeTenant === 'acme'
                ? 'Ask a question about Acme Corp policies, equipment, probation...'
                : 'Ask a question about Globex security guidelines, compliance...'
            }
            className="flex-1 bg-transparent resize-none text-sm px-3 py-2 text-slate-100 placeholder-slate-500 focus:outline-none max-h-24 leading-relaxed font-sans"
          />

          {/* Character Counter (0/500) */}
          <div
            className="shrink-0 px-2.5 py-1.5 text-[11px] font-mono select-none rounded-xl bg-white/[0.04] border border-white/10 flex items-center justify-center transition-colors"
            title="Message length (max 500 characters)"
          >
            <span
              className={
                inputQuery.length >= 500
                  ? 'text-red-400 font-bold'
                  : inputQuery.length >= 450
                    ? 'text-amber-400 font-semibold'
                    : 'text-slate-300'
              }
            >
              {inputQuery.length}
            </span>
            <span className="text-slate-500">/500</span>
          </div>

          <button
            type="submit"
            disabled={!inputQuery.trim() || isLoading}
            className={`px-4 py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 transition-all disabled:opacity-40 disabled:cursor-not-allowed ${tokens.primaryButtonClass}`}
          >
            <Send className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Send</span>
          </button>
        </form>
      </div>
    </div>
  );
};
