"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Navbar() {
  const pathname = usePathname();

  const navItems = [
    { href: "/chat", label: "AI对话" },
    { href: "/documents", label: "知识空间" },
    { href: "/settings", label: "高级配置" },
  ];

  return (
    <nav className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 shadow-sm transition-colors">
      <div className="max-w-7xl mx-auto px-3 sm:px-4 md:px-6 lg:px-8">
        <div className="flex justify-between items-center h-14 sm:h-16">
          <div className="flex items-center gap-2">
            {pathname === "/chat" && (
              <button
                type="button"
                onClick={() => {
                  window.dispatchEvent(new CustomEvent("openChatSidebar"));
                }}
                className="md:hidden inline-flex items-center justify-center p-2 rounded-md text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500 dark:focus:ring-blue-400"
                aria-label="打开对话历史"
                title="对话历史"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                  />
                </svg>
              </button>
            )}

            <Link
              href="/chat"
              className="flex items-center space-x-2 text-base sm:text-lg md:text-xl font-bold text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
            >
              <span>context-engine</span>
            </Link>
          </div>

          <div className="hidden md:flex items-center space-x-1">
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? "bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
                      : "text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-800"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>

          <div className="md:hidden flex items-center">
            <button
              type="button"
              onClick={() => {
                const menu = document.getElementById("mobile-menu");
                if (menu) {
                  const isHidden = menu.classList.contains("hidden");
                  if (isHidden) {
                    menu.classList.remove("hidden");
                    menu.style.maxHeight = menu.scrollHeight + "px";
                  } else {
                    menu.style.maxHeight = "0";
                    setTimeout(() => menu.classList.add("hidden"), 300);
                  }
                }
              }}
              className="inline-flex items-center justify-center p-2.5 min-w-[44px] min-h-[44px] rounded-md text-gray-600 dark:text-gray-300 active:text-gray-900 dark:active:text-gray-100 active:bg-gray-100 dark:active:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500 dark:focus:ring-blue-400 transition-colors"
              aria-label="打开菜单"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div
        id="mobile-menu"
        className="hidden md:hidden border-t border-gray-200 dark:border-gray-700 transition-all duration-300 ease-in-out overflow-hidden"
      >
        <div className="px-3 pt-2 pb-3 space-y-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block px-3 py-2.5 rounded-md text-base font-medium min-h-[44px] flex items-center transition-colors ${
                  isActive
                    ? "bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
                    : "text-gray-600 dark:text-gray-300 active:bg-gray-100 dark:active:bg-gray-800"
                }`}
                onClick={() => {
                  const menu = document.getElementById("mobile-menu");
                  if (menu) menu.classList.add("hidden");
                }}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}

