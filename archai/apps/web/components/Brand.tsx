import {House} from 'lucide-react';
import Link from 'next/link';
export default function Brand({compact=false}:{compact?:boolean}){return <Link className="brand" href="/" aria-label="ArchAI home"><span className="brand-mark"><House size={21} strokeWidth={1.8}/></span>{!compact&&<span>Arch<span className="brand-ai">AI</span></span>}</Link>}
