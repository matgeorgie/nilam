import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'ArchAI — A better way to imagine home',description:'Turn your ideas into intelligent 2D & 3D house plans. A conceptual architecture workspace.',icons:{icon:'/favicon.svg'}};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
