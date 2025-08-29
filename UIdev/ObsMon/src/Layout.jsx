import { useState } from "react";
import { Menu } from "lucide-react"; // hamburger icon

export default function Layout({ children }) {
    const [open, setOpen] = useState(false);

    return (
        <div className="flex h-screen">
            {/* Sidebar */}
            <div
                className={`fixed top-0 left-0 h-full bg-gray-800 text-white p-4 transition-transform duration-300
        ${open ? "translate-x-0" : "-translate-x-full"} 
        md:relative md:translate-x-0 md:w-64`}
            >
                <p className="font-bold">Sidebar content here</p>
            </div>

            {/* Content */}
            <div className="flex-1 p-4 md:ml-64">
                {/* Hamburger only shows on mobile */}
                <button
                    className="md:hidden mb-4"
                    onClick={() => setOpen(!open)}
                >
                    <Menu />
                </button>
                {children}
            </div>
        </div>
    );
}
