/* Yoink Caddie — client-side style engine.
   Crown demo pages embed course packs (#cpacks) and this script; it injects a
   style picker and re-dresses every hole from the same measurements. The Book
   is the locked brand default; Gen 11 restores the server-rendered Crown art.
   Choice persists per browser via localStorage. */
(function(){



function rng(seed){ var s=0; for(var i=0;i<seed.length;i++) s=(s*31+seed.charCodeAt(i))>>>0;
  return function(){ s=(s+0x6D2B79F5)>>>0; var t=Math.imul(s^(s>>>15),1|s);
    t=(t+Math.imul(t^(t>>>7),61|t))^t; return ((t^(t>>>14))>>>0)/4294967296; }; }
function smooth(pts, closed){
  var p=pts.slice(); if(closed && (p[0][0]!==p[p.length-1][0]||p[0][1]!==p[p.length-1][1])) p.push(p[0]);
  if(closed) p.pop();
  var n=p.length, d='M'+p[0][0].toFixed(1)+','+p[0][1].toFixed(1);
  function at(i){ return p[((i%n)+n)%n]; }
  var end=closed?n:n-1;
  for(var i=0;i<end;i++){
    var p0=at(i-1),p1=at(i),p2=at(i+1),p3=at(i+2);
    if(!closed){ if(i===0)p0=p1; if(i===n-2)p3=p2; }
    var c1=[p1[0]+(p2[0]-p0[0])/6, p1[1]+(p2[1]-p0[1])/6];
    var c2=[p2[0]-(p3[0]-p1[0])/6, p2[1]-(p3[1]-p1[1])/6];
    d+='C'+c1[0].toFixed(1)+','+c1[1].toFixed(1)+' '+c2[0].toFixed(1)+','+c2[1].toFixed(1)+' '+p2[0].toFixed(1)+','+p2[1].toFixed(1);
  }
  return d+(closed?'Z':'');
}
var segs=[], totalLen=0;
function rebuildArc(){ segs=[]; totalLen=0; for(var i=0;i<G.line.length-1;i++){ var a=G.line[i],b=G.line[i+1];
  var L=Math.hypot(b[0]-a[0],b[1]-a[1]); segs.push({a:a,b:b,L:L}); totalLen+=L; } }
function lineAt(arc){ var t=Math.max(0,Math.min(arc,totalLen)), i=0;
  while(i<segs.length-1 && t>segs[i].L){ t-=segs[i].L; i++; }
  var s=segs[i], f=t/s.L;
  return { p:[s.a[0]+(s.b[0]-s.a[0])*f, s.a[1]+(s.b[1]-s.a[1])*f],
           d:[(s.b[0]-s.a[0])/s.L,(s.b[1]-s.a[1])/s.L] }; }
function corridor(a0,a1,wFn,R){
  var left=[], right=[], steps=26;
  for(var i=0;i<=steps;i++){
    var arc=a0+(a1-a0)*i/steps, q=lineAt(arc), w=wFn(arc)*(0.94+(R?R():0.5)*0.12);
    left.push([q.p[0]-q.d[1]*w, q.p[1]+q.d[0]*w]);
    right.push([q.p[0]+q.d[1]*w, q.p[1]-q.d[0]*w]);
  }
  return left.concat(right.reverse());
}
function fwWidth(arc){ var t=(arc-G.fwStart)/(totalLen-G.fwStart);
  return 15+14*Math.sin(Math.min(1,Math.max(0,t))*Math.PI)*1.05; }
function treeSpots(R){
  var out=[];
  G.stands.forEach(function(st){
    var n=Math.max(2,st.count+1);
    for(var i=0;i<n;i++){
      var arc=st.a0+(st.a1-st.a0)*(i+0.5)/n, q=lineAt(arc);
      var off=st.d+6+R()*10;
      out.push([q.p[0]+q.d[1]*off*st.side*-1, q.p[1]-q.d[0]*off*st.side*-1, 8+R()*7]);
    }
  });
  return out;
}
function inset(pts, f){
  var cx=0, cy=0; pts.forEach(function(p){cx+=p[0];cy+=p[1];});
  cx/=pts.length; cy/=pts.length;
  return pts.map(function(p){ return [cx+(p[0]-cx)*f, cy+(p[1]-cy)*f]; });
}




var G=null;   // page-space geometry, set per hole by renderBook

function renderBook(el, H, meta){
  var target=el.id || (el.id='ha'+H.hole);
  var INK='#14432A', MUT='#6D7770', FAINT='#9AA39C', ACID='#C7F24A', PENCIL='#55584F', TREE='#D6E0BE';
  var SUF='_'+target;
  var R=rng((meta.key||'course')+':'+H.hole+':book');

  // ---- fit raw yards geometry into the page art zone ----
  var pts=[];
  function eat(a){ (a||[]).forEach(function(p){ pts.push(p); }); }
  eat(H.line); eat(H.green); eat(H.tees);
  (H.bunkers||[]).forEach(eat); (H.waters||[]).forEach(eat);
  var xs=pts.map(function(p){return p[0];}), ys=pts.map(function(p){return p[1];});
  var minx=Math.min.apply(0,xs)-18, maxx=Math.max.apply(0,xs)+18;
  var miny=Math.min.apply(0,ys)-14, maxy=Math.max.apply(0,ys)+6;
  var s=Math.min(226/(maxx-minx), 484/(maxy-miny), H.par===3?2.1:1.35);
  var tx=-20-s*(minx+maxx)/2, ty=-16-s*maxy;
  function T(p){ return [p[0]*s+tx, p[1]*s+ty]; }
  function Tp(a){ return (a||[]).map(T); }

  G={ line:Tp(H.line), green:Tp(H.green), tees:Tp(H.tees),
      bunkers:(H.bunkers||[]).map(Tp), waters:(H.waters||[]).map(Tp),
      stands:(H.stands||[]).map(function(st){ return {d:st.d*s, a0:st.a0*s, a1:st.a1*s, side:st.side, count:st.count}; }),
      fwStart:(H.fw_start!=null?H.fw_start*s:null), bendAt:(H.bend?H.bend.at*s:null) };
  rebuildArc();

  var defs = "<defs>"
    +"<pattern id='bkgrid"+SUF+"' width='11' height='11' patternUnits='userSpaceOnUse'><path d='M11,0 L0,0 0,11' fill='none' stroke='#E4E1D2' stroke-width='0.5'/></pattern>"
    +"<filter id='bkpencil"+SUF+"'><feTurbulence type='fractalNoise' baseFrequency='0.09' numOctaves='2' seed='31'/><feDisplacementMap in='SourceGraphic' scale='1.6'/></filter>"
    +"<clipPath id='bkclip"+SUF+"'><rect x='24' y='-188' width='72' height='72'/></clipPath>"
    +"</defs>";
  var s2 = "<rect x='-155' y='-565' width='260' height='615' fill='#F6F4EB'/>";
  s2 += "<rect x='-136' y='-565' width='241' height='615' fill='url(#bkgrid"+SUF+")'/>";
  for(var i=0;i<13;i++){
    var y=-548+i*47;
    s2 += "<circle cx='-147' cy='"+y+"' r='3.4' fill='#F6F4EB' stroke='"+FAINT+"' stroke-width='1.2'/>";
    s2 += "<path d='M-147,"+(y-3.4)+" A6,6 0 0 1 -141,"+y+"' fill='none' stroke='"+MUT+"' stroke-width='1.4'/>";
  }
  s2 += "<line x1='-136' y1='-565' x2='-136' y2='50' stroke='#D9D5C4' stroke-width='0.8'/>";

  // ---- hole art ----
  if(G.fwStart!=null){
    s2 += "<path d='"+smooth(corridor(16*s,G.fwStart,function(a){return 12*s;},null),true)+"' fill='none' stroke='"+INK+"' stroke-width='0.7' stroke-dasharray='2 2.6' opacity='0.55'/>";
    var fwd = smooth(corridor(G.fwStart,totalLen-8*s,fwWidth,null),true);
    s2 += "<path d='"+fwd+"' fill='#EAEFE0' stroke='"+INK+"' stroke-width='1'/>";
  }
  G.waters.forEach(function(w){
    s2 += "<path d='"+smooth(w,true)+"' fill='#DEE9EA' stroke='"+INK+"' stroke-width='1.1'/>";
    s2 += "<path d='"+smooth(inset(w.slice(0,-1),0.72),true)+"' fill='none' stroke='#9CBEC2' stroke-width='0.6'/>";
    s2 += "<path d='"+smooth(inset(w.slice(0,-1),0.45),true)+"' fill='none' stroke='#9CBEC2' stroke-width='0.5' opacity='0.7'/>";
  });
  G.bunkers.forEach(function(b){
    s2 += "<path d='"+smooth(b,true)+"' fill='#F0EAD6' stroke='"+INK+"' stroke-width='0.9'/>";
  });
  s2 += "<path d='"+smooth(G.green,true)+"' fill='#DCE7CE' stroke='"+INK+"' stroke-width='1.4'/>";
  var pin=T([ (H.green.reduce(function(a,p){return a+p[0];},0)/H.green.length),
              (H.green.reduce(function(a,p){return a+p[1];},0)/H.green.length) ]);
  s2 += "<circle cx='"+pin[0].toFixed(1)+"' cy='"+pin[1].toFixed(1)+"' r='2.2' fill='"+ACID+"' stroke='"+INK+"' stroke-width='0.9'/>";
  G.tees.forEach(function(t){ s2 += "<rect x='"+(t[0]-3).toFixed(1)+"' y='"+(t[1]-1.8).toFixed(1)+"' width='6' height='3.6' fill='none' stroke='"+INK+"' stroke-width='0.9'/>"; });
  var trs=Math.min(1.15,Math.max(0.8,s));
  treeSpots(R).forEach(function(t){
    t[2]=t[2]*trs;
    var ell = "<ellipse cx='"+t[0].toFixed(1)+"' cy='"+t[1].toFixed(1)+"' rx='"+(t[2]*1.05).toFixed(1)+"' ry='"+(t[2]*0.5).toFixed(1)+"'/>"
      +"<ellipse cx='"+(t[0]-t[2]*0.55).toFixed(1)+"' cy='"+(t[1]+2.6).toFixed(1)+"' rx='"+(t[2]*0.55).toFixed(1)+"' ry='"+(t[2]*0.3).toFixed(1)+"'/>"
      +"<ellipse cx='"+(t[0]+t[2]*0.55).toFixed(1)+"' cy='"+(t[1]+3).toFixed(1)+"' rx='"+(t[2]*0.5).toFixed(1)+"' ry='"+(t[2]*0.28).toFixed(1)+"'/>";
    s2 += "<g stroke='"+INK+"' stroke-width='1.8' fill='"+TREE+"'>"+ell+"</g>";
    s2 += "<g fill='"+TREE+"' stroke='none'>"+ell+"</g>";
  });
  // the line: single dashed ink, arrowhead at the green
  s2 += "<path d='"+smooth(G.line,false)+"' fill='none' stroke='"+INK+"' stroke-width='1.7' stroke-dasharray='8 5' stroke-linecap='round'/>";
  var tip=lineAt(totalLen), bk=lineAt(totalLen-6);
  var dx=tip.p[0]-bk.p[0], dy=tip.p[1]-bk.p[1], dl=Math.hypot(dx,dy)||1; dx/=dl; dy/=dl;
  var ax=tip.p[0], ay=tip.p[1];
  s2 += "<path d='M"+(ax-4*dx-3*dy).toFixed(1)+","+(ay-4*dy+3*dx).toFixed(1)+" L"+ax.toFixed(1)+","+ay.toFixed(1)
      +" L"+(ax-4*dx+3*dy).toFixed(1)+","+(ay-4*dy-3*dx).toFixed(1)+"' fill='none' stroke='"+INK+"' stroke-width='1.3'/>";
  // pips each 100 yards
  for(var a=100; a<H.total-24; a+=100){
    var q=lineAt(a*s).p;
    s2 += "<circle cx='"+q[0].toFixed(1)+"' cy='"+q[1].toFixed(1)+"' r='2.2' fill='#F6F4EB' stroke='"+INK+"' stroke-width='0.9'/>";
    s2 += "<text x='"+(q[0]-6.5).toFixed(1)+"' y='"+(q[1]+2.2).toFixed(1)+"' font-size='6.2' font-family='Archivo, sans-serif' font-weight='700' fill='"+MUT+"' text-anchor='end'>"+a+"</text>";
  }
  function tick(arcY,label){
    var q=lineAt(arcY*s), w=(G.fwStart!=null?fwWidth(arcY*s):12*s)+7, pp=[q.d[1],-q.d[0]];
    var x1=q.p[0]-pp[0]*w, y1=q.p[1]-pp[1]*w, x2=q.p[0]+pp[0]*w, y2=q.p[1]+pp[1]*w;
    return "<path d='M"+x1.toFixed(1)+","+y1.toFixed(1)+" L"+x2.toFixed(1)+","+y2.toFixed(1)+"' stroke='"+INK+"' stroke-width='0.7' stroke-dasharray='2 2'/>"
      +"<text x='"+(x2+4).toFixed(1)+"' y='"+(y2+2.2).toFixed(1)+"' font-size='7' font-family='Archivo, sans-serif' font-weight='700' fill='"+INK+"'>"+label+"</text>";
  }
  if(H.fw_start!=null) s2 += tick(H.fw_start, H.fw_start+' FWY');
  if(H.bend && Math.abs(H.bend.at-(H.fw_start||-999))>18) s2 += tick(H.bend.at, H.bend.at+' TURN');
  // carry notes, right margin
  (H.carries||[]).forEach(function(c){
    if(c.kind==='fairway') return;
    if(c.kind==='sand' && c.at>H.total-30) return;
    var q=lineAt(c.at*s).p;
    var yy=Math.max(-500,Math.min(-30,q[1]));
    s2 += "<text x='96' y='"+yy.toFixed(1)+"' font-size='7' font-family='Archivo, sans-serif' font-weight='700' fill='"+INK+"' text-anchor='end'>CARRY "+c.at+" &#183; "+c.kind.toUpperCase()+"</text>";
  });
  // pencil live note (par 4/5): mid-approach position
  if(H.par>3){
    var frac=0.62, me=lineAt(totalLen*frac).p, rem=Math.round(H.total*(1-frac));
    s2 += "<circle cx='"+me[0].toFixed(1)+"' cy='"+me[1].toFixed(1)+"' r='2.6' fill='"+ACID+"' stroke='"+INK+"' stroke-width='1'/>";
    s2 += "<g filter='url(#bkpencil"+SUF+")'>";
    s2 += "<circle cx='-105' cy='"+(me[1]-2).toFixed(1)+"' r='13' fill='none' stroke='"+PENCIL+"' stroke-width='1.3'/>";
    s2 += "<path d='M-92,"+(me[1]-2).toFixed(1)+" L"+(me[0]-6).toFixed(1)+","+(me[1]-0.5).toFixed(1)+"' stroke='"+PENCIL+"' stroke-width='0.9' fill='none'/>";
    s2 += "</g>";
    s2 += "<text x='-105' y='"+(me[1]+3).toFixed(1)+"' font-size='13' font-family='Caveat, cursive' font-weight='600' fill='"+PENCIL+"' text-anchor='middle'>"+rem+"</text>";
    s2 += "<text x='-105' y='"+(me[1]-19).toFixed(1)+"' font-size='9' font-family='Caveat, cursive' fill='"+PENCIL+"' text-anchor='middle'>to ctr</text>";
  }
  // green detail box
  var gs=0, gc=pin;
  (function(){
    var gxs=H.green.map(function(p){return p[0];}), gys=H.green.map(function(p){return p[1];});
    var gw=Math.max.apply(0,gxs)-Math.min.apply(0,gxs), gh=Math.max.apply(0,gys)-Math.min.apply(0,gys);
    gs=52/Math.max(gw,gh);
    var rawc=[(Math.max.apply(0,gxs)+Math.min.apply(0,gxs))/2,(Math.max.apply(0,gys)+Math.min.apply(0,gys))/2];
    s2 += "<rect x='24' y='-188' width='72' height='72' fill='#FBFAF4' stroke='"+INK+"' stroke-width='1.1'/>";
    s2 += "<rect x='24' y='-188' width='72' height='72' fill='url(#bkgrid"+SUF+")'/>";
    s2 += "<g clip-path='url(#bkclip"+SUF+")'><g transform='translate(60,-152) scale("+gs.toFixed(3)+") translate("+(-rawc[0]).toFixed(1)+","+(-rawc[1]).toFixed(1)+")'>";
    s2 += "<path d='"+smooth(H.green,true)+"' fill='#DCE7CE' stroke='"+INK+"' stroke-width='"+(1.2/gs).toFixed(2)+"'/>";
    (H.bunkers||[]).forEach(function(b){
      var bc=[b.reduce(function(a,p){return a+p[0];},0)/b.length, b.reduce(function(a,p){return a+p[1];},0)/b.length];
      if(Math.hypot(bc[0]-rawc[0],bc[1]-rawc[1])<42)
        s2 += "<path d='"+smooth(b,true)+"' fill='#F0EAD6' stroke='"+INK+"' stroke-width='"+(0.8/gs).toFixed(2)+"'/>";
    });
    s2 += "<circle cx='"+rawc[0].toFixed(1)+"' cy='"+rawc[1].toFixed(1)+"' r='"+(1.8/gs).toFixed(2)+"' fill='"+ACID+"' stroke='"+INK+"' stroke-width='"+(0.7/gs).toFixed(2)+"'/>";
    s2 += "</g></g>";
  })();
  s2 += "<text x='60' y='-106' font-size='6.4' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='0.8' fill='"+INK+"' text-anchor='middle'>GREEN &#183; "+(H.depth||'?')+" DEEP</text>";

  // header
  var bkNm=(meta.name||'THE BOOK')
    .replace(/\s+(state park|country club|golf course|golf club|golf links|golf center|park golf course)$/i,'')
    .toUpperCase().slice(0,26);
  var bkFs=Math.max(6.5, Math.min(9.5, (125/Math.max(1,bkNm.length)-1.8)/0.62));
  var hn=(H.hole<10?'0':'')+H.hole;
  s2 += "<rect x='-128' y='-556' width='30' height='30' fill='none' stroke='"+INK+"' stroke-width='1.4'/>";
  s2 += "<text x='-113' y='-533' font-size='"+(H.hole<10?22:18)+"' font-family='Archivo, sans-serif' font-weight='900' fill='"+INK+"' text-anchor='middle'>"+H.hole+"</text>";
  s2 += "<g font-family='Archivo, sans-serif'>";
  s2 += "<text x='-90' y='-544' font-size='"+bkFs.toFixed(1)+"' font-weight='700' letter-spacing='1.8' fill='"+INK+"'>"+bkNm+"</text>";
  s2 += "<text x='-90' y='-532' font-size='6.6' font-weight='700' letter-spacing='1' fill='"+MUT+"'>YOINK &#183; THE BOOK</text>";
  s2 += "<text x='96' y='-544' font-size='6.4' font-weight='700' fill='"+FAINT+"' text-anchor='end'>PAGE "+hn+" / 18</text>";
  s2 += "</g>";
  s2 += "<line x1='-128' y1='-524' x2='-46' y2='-524' stroke='"+INK+"' stroke-width='1'/>";
  var vfs=Math.min(10.5, 216/(0.42*H.sign.length));
  s2 += "<text x='-128' y='0' font-size='"+vfs.toFixed(1)+"' font-family='Caveat, cursive' font-weight='600' fill='"+PENCIL+"'>"+H.sign+"</text>";

  // scorecard strip
  var cols=[['HOLE',''+H.hole,22],['PAR',''+H.par,22],['HCP','&#8212;',22],['BACK',''+H.yards.back,30],['MID',''+H.yards.mid,30],['FWD',''+H.yards.front,30],['SCORE','',46]];
  var x0=-128, y0=8, hh=32, tot=0; cols.forEach(function(c){tot+=c[2];});
  s2 += "<rect x='"+x0+"' y='"+y0+"' width='"+tot+"' height='"+hh+"' fill='#FBFAF4' stroke='"+INK+"' stroke-width='1.2'/>";
  var cx=x0;
  cols.forEach(function(c,i){
    if(i>0) s2 += "<line x1='"+cx+"' y1='"+y0+"' x2='"+cx+"' y2='"+(y0+hh)+"' stroke='"+INK+"' stroke-width='0.7'/>";
    s2 += "<text x='"+(cx+c[2]/2)+"' y='"+(y0+10)+"' font-size='5.6' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='0.8' fill='"+MUT+"' text-anchor='middle'>"+c[0]+"</text>";
    if(c[1]) s2 += "<text x='"+(cx+c[2]/2)+"' y='"+(y0+25)+"' font-size='11.5' font-family='Archivo, sans-serif' font-weight='900' fill='"+INK+"' text-anchor='middle'>"+c[1]+"</text>";
    cx+=c[2];
  });
  s2 += "<line x1='"+x0+"' y1='"+(y0+14)+"' x2='"+(x0+tot)+"' y2='"+(y0+14)+"' stroke='"+INK+"' stroke-width='0.6'/>";
  s2 += "<g transform='translate(88,14) scale(0.16)'><path d='M50,5 c4.4,0 7.3,3.4 6.9,7.7 L52.7,103 h-5.4 L43.1,12.7 C42.7,8.4 45.6,5 50,5 Z' fill='"+INK+"'/><path d='M56.6,11 l31,9.6 -31,9.6 z' fill='"+ACID+"'/><circle cx='50' cy='125.5' r='9.6' fill='"+INK+"'/></g>";

  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s2;
}




// ---- shared page fit for the framed styles (Estate / Landform / Evening) ----
function stripName(n){
  return String(n).replace(/\s+(state park|country club|golf course|golf club|golf links|golf center|park golf course|golf and tennis club|golf and country club)$/i,'')
    .toUpperCase().slice(0,26);
}
function fitPage(H){
  var pts=[];
  function eat(a){ (a||[]).forEach(function(p){ pts.push(p); }); }
  eat(H.line); eat(H.green); eat(H.tees);
  (H.bunkers||[]).forEach(eat); (H.waters||[]).forEach(eat);
  var xs=pts.map(function(p){return p[0];}), ys=pts.map(function(p){return p[1];});
  var minx=Math.min.apply(0,xs)-20, maxx=Math.max.apply(0,xs)+20;
  var miny=Math.min.apply(0,ys)-16, maxy=Math.max.apply(0,ys)+6;
  var s=Math.min(212/(maxx-minx), 452/(maxy-miny), H.par===3?2.0:1.3);
  var tx=-24-s*(minx+maxx)/2, ty=-64-s*maxy;
  function T(p){ return [p[0]*s+tx, p[1]*s+ty]; }
  function Tp(a){ return (a||[]).map(T); }
  G={ line:Tp(H.line), green:Tp(H.green), tees:Tp(H.tees),
      bunkers:(H.bunkers||[]).map(Tp), waters:(H.waters||[]).map(Tp),
      stands:(H.stands||[]).map(function(st){ return {d:st.d*s, a0:st.a0*s, a1:st.a1*s, side:st.side, count:st.count}; }),
      fwStart:(function(){ var f=(H.fw_start!=null)?H.fw_start:(H.fw&&H.fw[0]?H.fw[0][0]:null); return f!=null?f*s:null; })(), bendAt:(H.bend?H.bend.at*s:null) };
  rebuildArc();
  return s;
}

function renderEstate(el,H,meta){
  var s_=fitPage(H);
  var SUF='_'+el.id;
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':estate');
  var PAPER='#F3EDDD', PLATE='#CBC2A8', INK='#243B2E', WATER='#3E5A64', GOLD='#A98B2D';
  var defs="<defs>"
    +"<pattern id='eh1"+SUF+"' width='3.6' height='3.6' patternUnits='userSpaceOnUse' patternTransform='rotate(37)'><line x1='0' y1='0' x2='0' y2='3.6' stroke='"+INK+"' stroke-width='0.5' opacity='0.55'/></pattern>"
    +"<pattern id='eh2"+SUF+"' width='3.2' height='3.2' patternUnits='userSpaceOnUse' patternTransform='rotate(-49)'><line x1='0' y1='0' x2='0' y2='3.2' stroke='"+INK+"' stroke-width='0.45' opacity='0.5'/></pattern>"
    +"<pattern id='eh3"+SUF+"' width='6.5' height='6.5' patternUnits='userSpaceOnUse' patternTransform='rotate(37)'><line x1='0' y1='0' x2='0' y2='6.5' stroke='"+INK+"' stroke-width='0.4' opacity='0.35'/></pattern>"
    +"<pattern id='estip"+SUF+"' width='4.4' height='4.4' patternUnits='userSpaceOnUse'><circle cx='1' cy='1.2' r='0.5' fill='"+INK+"' opacity='0.55'/><circle cx='3.1' cy='3.3' r='0.42' fill='"+INK+"' opacity='0.45'/><circle cx='2.2' cy='0.4' r='0.3' fill='"+INK+"' opacity='0.3'/></pattern>"
    +"<filter id='ewob"+SUF+"'><feTurbulence type='fractalNoise' baseFrequency='0.11' numOctaves='2' seed='4'/><feDisplacementMap in='SourceGraphic' scale='1.1'/></filter>"
    +"</defs>";
var ORD=['First','Second','Third','Fourth','Fifth','Sixth','Seventh','Eighth','Ninth','Tenth','Eleventh','Twelfth','Thirteenth','Fourteenth','Fifteenth','Sixteenth','Seventeenth','Eighteenth'];
  var estNm=stripName(meta.name||'THE COURSE');
  var estFs=Math.max(7,Math.min(12.5,(148/Math.max(1,estNm.length)-3.2)/0.62));
  var s="<rect x='-155' y='-565' width='260' height='615' fill='"+PAPER+"'/>";
  // plate mark + ruled border
  s+="<rect x='-146' y='-556' width='242' height='597' fill='none' stroke='"+PLATE+"' stroke-width='1.6'/>";
  s+="<rect x='-140' y='-550' width='230' height='585' fill='none' stroke='"+INK+"' stroke-width='1.1'/>";
  s+="<rect x='-137' y='-547' width='224' height='579' fill='none' stroke='"+INK+"' stroke-width='0.35'/>";

  // rough: double-hatched ground, fairway carved out of it
  var roughD=smooth(corridor(4,totalLen,function(a){return safeFw(a)+23;},R),true);
  s+="<g filter='url(#ewob"+SUF+")'>";
  s+="<path d='"+roughD+"' fill='url(#eh1"+SUF+")'/>";
  s+="<path d='"+roughD+"' fill='url(#eh2"+SUF+")'/>";
  s+="<path d='"+roughD+"' fill='none' stroke='"+INK+"' stroke-width='0.8'/>";
  if(G.fwStart!=null){
    var fwD=smooth(corridor(G.fwStart,totalLen-8,safeFw,null),true);
    s+="<path d='"+fwD+"' fill='"+PAPER+"'/>";
    s+="<path d='"+fwD+"' fill='url(#eh3"+SUF+")'/>";
    s+="<path d='"+fwD+"' fill='none' stroke='"+INK+"' stroke-width='0.9'/>";
  }
  s+="</g>";
  // approach/walk before the fairway: pale stipple path
  s+="<path d='"+smooth(corridor(14,(G.fwStart!=null?G.fwStart+6:totalLen*0.55),function(a){return 8;},null),true)+"' fill='url(#estip"+SUF+")' opacity='0.35'/>";

  // water: engraved concentric shorelines
  G.waters.forEach(function(w){
    s+="<g filter='url(#ewob"+SUF+")'>";
    s+="<path d='"+smooth(w,true)+"' fill='"+PAPER+"' stroke='"+WATER+"' stroke-width='1.1'/>";
    [0.92,0.82,0.71,0.59,0.46,0.32,0.18].forEach(function(f,i){
      s+="<path d='"+smooth(inset(w.slice(0,-1),f),true)+"' fill='none' stroke='"+WATER+"' stroke-width='"+(0.7-i*0.06)+"' opacity='"+(0.85-i*0.1)+"'/>";
    });
    s+="</g>";
  });
  // bunkers: stipple with a lipped edge
  G.bunkers.forEach(function(b){
    s+="<g filter='url(#ewob"+SUF+")'><path d='"+smooth(b,true)+"' fill='url(#estip"+SUF+")' stroke='"+INK+"' stroke-width='0.9'/>";
    s+="<path d='"+smooth(inset(b.slice(0,-1),0.6),true)+"' fill='none' stroke='"+INK+"' stroke-width='0.4' opacity='0.5'/></g>";
  });
  // green: contour-hatched putting surface
  s+="<g filter='url(#ewob"+SUF+")'>";
  s+="<path d='"+smooth(G.green,true)+"' fill='"+PAPER+"' stroke='"+INK+"' stroke-width='1.2'/>";
  [0.78,0.55,0.32].forEach(function(f){
    s+="<path d='"+smooth(inset(G.green.slice(0,-1),f),true)+"' fill='none' stroke='"+INK+"' stroke-width='0.45' opacity='0.55'/>";
  });
  s+="</g>";
  // pin: gilded
  var gp=lineAt(totalLen).p;
  s+="<line x1='"+gp[0]+"' y1='"+gp[1]+"' x2='"+gp[0]+"' y2='"+(gp[1]-13)+"' stroke='"+INK+"' stroke-width='0.9'/>";
  s+="<path d='M"+gp[0]+","+(gp[1]-13)+" l7.5,2.6 -7.5,2.6 z' fill='"+GOLD+"' stroke='"+INK+"' stroke-width='0.5'/>";
  s+="<circle cx='"+gp[0]+"' cy='"+gp[1]+"' r='1.5' fill='"+GOLD+"' stroke='"+INK+"' stroke-width='0.6'/>";

  // trees: antique estate rounds — scalloped crown, SE shade
  treeSpots(R).forEach(function(t){
    var x=t[0],y=t[1],r=t[2]*0.92;
    var d='', n=9;
    for(var i=0;i<n;i++){ var a0=i/n*Math.PI*2, a1=(i+1)/n*Math.PI*2;
      var mx=x+Math.cos((a0+a1)/2)*r*1.24, my=y+Math.sin((a0+a1)/2)*r*0.72;
      var x1=x+Math.cos(a1)*r, y1=y+Math.sin(a1)*r*0.58;
      d+=(i===0?('M'+(x+r)+','+y):'')+' Q'+mx.toFixed(1)+','+my.toFixed(1)+' '+x1.toFixed(1)+','+y1.toFixed(1);
    }
    s+="<g filter='url(#ewob"+SUF+")'><path d='"+d+"' fill='"+PAPER+"' stroke='"+INK+"' stroke-width='0.9'/>";
    for(var k=0;k<4;k++){
      var f=0.25+k*0.16;
      s+="<path d='M"+(x+r*f*0.5)+","+(y+r*0.5*f+1)+" q"+(r*0.45)+","+(r*0.28)+" "+(r*(0.95-f*0.4))+","+(r*0.12)+"' fill='none' stroke='"+INK+"' stroke-width='0.4' opacity='0.6'/>";
    }
    s+="<circle cx='"+x+"' cy='"+(y+1)+"' r='0.8' fill='"+INK+"'/></g>";
  });
  // tees: small engraved rectangles
  G.tees.forEach(function(t){ s+="<rect x='"+(t[0]-3.6)+"' y='"+(t[1]-2)+"' width='7.2' height='4' fill='url(#eh3"+SUF+")' stroke='"+INK+"' stroke-width='0.7'/>"; });

  // the line of play: fine dash, oldstyle numerals
  s+="<path d='"+smooth(G.line,false)+"' fill='none' stroke='"+INK+"' stroke-width='0.7' stroke-dasharray='5 3.4'/>";
  var pips=[]; for(var pa=100; pa<H.total-24; pa+=100) pips.push(pa);
  pips.forEach(function(a){ var q=lineAt(a*s_).p;
    s+="<circle cx='"+q[0]+"' cy='"+q[1]+"' r='1.4' fill='"+PAPER+"' stroke='"+INK+"' stroke-width='0.7'/>";
    s+="<text x='"+(q[0]-5.5)+"' y='"+(q[1]+2.4)+"' font-size='6.8' font-family='Fraunces, Georgia, serif' font-style='italic' fill='"+INK+"' text-anchor='end'>"+a+"</text>"; });

  // cartouche
  s+="<g>";
  s+="<path d='M-84,-24 L58,-24 L64,-18 L64,26 L58,32 L-84,32 L-90,26 L-90,-18 Z' fill='"+PAPER+"' stroke='"+INK+"' stroke-width='1.1'/>";
  s+="<path d='M-86,-20 L60,-20 L60,28 L-86,28 Z' fill='none' stroke='"+INK+"' stroke-width='0.4'/>";
  s+="<text x='-13' y='-6' font-size='"+estFs.toFixed(1)+"' font-family='Fraunces, Georgia, serif' font-weight='600' letter-spacing='3.2' fill='"+INK+"' text-anchor='middle'>"+estNm+"</text>";
  s+="<line x1='-56' y1='1.5' x2='30' y2='1.5' stroke='"+GOLD+"' stroke-width='1'/>";
  s+="<circle cx='-13' cy='1.5' r='1.8' fill='"+GOLD+"'/>";
  s+="<text x='-13' y='13' font-size='7.5' font-family='Fraunces, Georgia, serif' font-style='italic' letter-spacing='1.4' fill='"+INK+"' text-anchor='middle'>Hole the "+(ORD[H.hole-1]||H.hole)+" &#183; Par "+H.par+" &#183; "+H.yards.mid+" Yards</text>";
  s+="<text x='-13' y='24' font-size='5.6' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='2.4' fill='"+GOLD+"' text-anchor='middle'>SURVEYED &amp; ENGRAVED FOR YOINK</text>";
  s+="</g>";
  // hole number, top right, engraved roundel
  s+="<circle cx='78' cy='-528' r='15' fill='"+PAPER+"' stroke='"+INK+"' stroke-width='1.1'/>";
  s+="<circle cx='78' cy='-528' r='12.2' fill='none' stroke='"+GOLD+"' stroke-width='0.9'/>";
  s+="<text x='78' y='-520.5' font-size='"+(H.hole>9?15:19)+"' font-family='Fraunces, Georgia, serif' font-weight='600' fill='"+INK+"' text-anchor='middle'>"+H.hole+"</text>";
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s;

}
function renderLandform(el,H,meta){
  var s_=fitPage(H);
  var SUF='_'+el.id;
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':landform');
  var FIELD='#0E1811', B1='#1A291D', B2='#25382A', B3='#324939', B4='#405C48', FW='#5C7D5B', GN='#7FA379', SAND='#C7AE79', WAT='#17313B', ACID='#C7F24A';
  var defs="<defs>"
    +"<filter id='lfsh1"+SUF+"' x='-40%' y='-40%' width='180%' height='180%'><feDropShadow dx='0' dy='4' stdDeviation='5' flood-color='#000000' flood-opacity='0.55'/></filter>"
    +"<filter id='lfsh2"+SUF+"' x='-40%' y='-40%' width='180%' height='180%'><feDropShadow dx='0' dy='3' stdDeviation='3.5' flood-color='#000000' flood-opacity='0.5'/></filter>"
    +"<filter id='lfsh3"+SUF+"' x='-40%' y='-40%' width='180%' height='180%'><feDropShadow dx='0' dy='2' stdDeviation='2' flood-color='#000000' flood-opacity='0.45'/></filter>"
    +"<linearGradient id='lfw"+SUF+"' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#224653'/><stop offset='1' stop-color='#122730'/></linearGradient>"
    +"<radialGradient id='lfvig"+SUF+"' cx='0.5' cy='0.42' r='0.75'><stop offset='0.62' stop-color='#000000' stop-opacity='0'/><stop offset='1' stop-color='#000000' stop-opacity='0.4'/></radialGradient>"
    +"</defs>";
  var lfNm=stripName(meta.name||'THE COURSE');
  var s="<rect x='-155' y='-565' width='260' height='615' fill='"+FIELD+"'/>";
  function band(pad, fill, filt){
    var d=smooth(corridor((G.fwStart!=null?Math.max(2,G.fwStart-(pad*26)):2), totalLen, function(a){return safeFw(a)+pad*9;}, null),true);
    return "<g filter='url(#"+filt+")'><path d='"+d+"' fill='"+fill+"'/><path d='"+d+"' fill='none' stroke='#B8D4A8' stroke-width='1' opacity='0.10'/></g>";
  }
  s+=band(3.4,B2,'lfsh1');
  s+=band(2.4,B3,'lfsh2');
  s+=band(1.5,B4,'lfsh2');
  // fairway plateau
  if(G.fwStart!=null){
    var fwD=smooth(corridor(G.fwStart,totalLen-8,safeFw,null),true);
    s+="<g filter='url(#lfsh3"+SUF+")'><path d='"+fwD+"' fill='"+FW+"'/><path d='"+fwD+"' fill='none' stroke='#CFE4BC' stroke-width='1' opacity='0.16'/></g>";
  }
  // water: recessed
  G.waters.forEach(function(w){
    var d=smooth(w,true);
    s+="<path d='"+d+"' fill='url(#lfw"+SUF+")'/>";
    s+="<path d='"+smooth(inset(w.slice(0,-1),0.9),true)+"' fill='none' stroke='#000000' stroke-width='2.6' opacity='0.35'/>";
    s+="<path d='"+d+"' fill='none' stroke='#6FA3AF' stroke-width='0.8' opacity='0.5'/>";
  });
  // bunkers: raised dishes
  G.bunkers.forEach(function(b){
    s+="<g filter='url(#lfsh3"+SUF+")'><path d='"+smooth(b,true)+"' fill='"+SAND+"'/></g>";
    s+="<path d='"+smooth(inset(b.slice(0,-1),0.55),true)+"' fill='none' stroke='#8F7A4C' stroke-width='0.8' opacity='0.7'/>";
  });
  // green: the brightest step
  s+="<g filter='url(#lfsh3"+SUF+")'><path d='"+smooth(G.green,true)+"' fill='"+GN+"'/><path d='"+smooth(G.green,true)+"' fill='none' stroke='#DFF0CE' stroke-width='1' opacity='0.25'/></g>";
  var gp=lineAt(totalLen).p;
  s+="<circle cx='"+gp[0]+"' cy='"+gp[1]+"' r='2' fill='"+ACID+"'/>";
  s+="<circle cx='"+gp[0]+"' cy='"+gp[1]+"' r='4.6' fill='none' stroke='"+ACID+"' stroke-width='0.7' opacity='0.55'/>";
  // trees: discs with long cast shadows to the east
  treeSpots(R).forEach(function(t){
    s+="<ellipse cx='"+(t[0]+t[2]*1.1)+"' cy='"+(t[1]+2.5)+"' rx='"+(t[2]*1.25)+"' ry='"+(t[2]*0.4)+"' fill='#000000' opacity='0.35'/>";
    s+="<circle cx='"+t[0]+"' cy='"+t[1]+"' r='"+(t[2]*0.72)+"' fill='"+B4+"'/>";
    s+="<circle cx='"+(t[0]-t[2]*0.2)+"' cy='"+(t[1]-t[2]*0.22)+"' r='"+(t[2]*0.4)+"' fill='"+FW+"' opacity='0.75'/>";
    s+="<circle cx='"+(t[0]-t[2]*0.3)+"' cy='"+(t[1]-t[2]*0.3)+"' r='"+(t[2]*0.14)+"' fill='#CFE4BC' opacity='0.5'/>";
  });
  // tees: two quiet steps
  G.tees.forEach(function(t){
    s+="<g filter='url(#lfsh3"+SUF+")'><rect x='"+(t[0]-5)+"' y='"+(t[1]-2.6)+"' width='10' height='5.2' rx='1.4' fill='"+B4+"'/></g>";
  });
  s+=lfMarksGen(H,s_,{ rule:'rgba(215,227,204,0.5)', text:'#E3EDD8', acc:'#C7F24A', muted:'#93A88E' });
  // vignette
  s+="<rect x='-155' y='-565' width='260' height='615' fill='url(#lfvig"+SUF+")'/>";
  // typography: airline-quiet
  s+="<text x='-140' y='-536' font-size='"+Math.max(6,Math.min(9,(150/Math.max(1,lfNm.length)-4.5)/0.62)).toFixed(1)+"' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='4.5' fill='#D7E3CC'>"+lfNm+"</text>";
  s+="<text x='-140' y='-522' font-size='6' font-family='Archivo, sans-serif' font-weight='500' letter-spacing='3' fill='#7C8F79'>YOINK CADDIE &#183; RENDERED FROM THE SURVEY</text>";
  s+="<line x1='-140' y1='24' x2='-96' y2='24' stroke='#7C8F79' stroke-width='0.7'/>";
  s+="<text x='-140' y='38' font-size='7' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='2.6' fill='#D7E3CC'>N&#176; "+H.hole+" &#8212; PAR "+H.par+" &#8212; "+H.yards.mid+" YDS</text>";
  s+="<text x='96' y='38' font-size='6' font-family='Archivo, sans-serif' font-weight='500' letter-spacing='2.4' fill='#7C8F79' text-anchor='end'>YOINK</text>";
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s;

}
function renderEvening(el,H,meta){
  var s_=fitPage(H);
  var SUF='_'+el.id;
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':oil');
  var defs="<defs>"
    +"<filter id='ob1"+SUF+"' x='-30%' y='-30%' width='160%' height='160%'><feTurbulence type='fractalNoise' baseFrequency='0.028' numOctaves='3' seed='3'/><feDisplacementMap in='SourceGraphic' scale='11'/></filter>"
    +"<filter id='ob2"+SUF+"' x='-30%' y='-30%' width='160%' height='160%'><feTurbulence type='fractalNoise' baseFrequency='0.055' numOctaves='2' seed='8'/><feDisplacementMap in='SourceGraphic' scale='6'/></filter>"
    +"<filter id='ob3"+SUF+"' x='-30%' y='-30%' width='160%' height='160%'><feTurbulence type='fractalNoise' baseFrequency='0.1' numOctaves='2' seed='15'/><feDisplacementMap in='SourceGraphic' scale='3'/><feGaussianBlur stdDeviation='0.4'/></filter>"
    +"<filter id='ocanvas"+SUF+"'><feTurbulence type='fractalNoise' baseFrequency='0.9 0.5' numOctaves='2' seed='2' result='n'/><feDiffuseLighting in='n' lighting-color='#FFF6E4' surfaceScale='0.9'><feDistantLight azimuth='235' elevation='58'/></feDiffuseLighting></filter>"
    +"<linearGradient id='ofw"+SUF+"' x1='0' y1='0.1' x2='1' y2='0.9'><stop offset='0' stop-color='#C8B36A'/><stop offset='0.45' stop-color='#8FA05B'/><stop offset='1' stop-color='#5F7A4A'/></linearGradient>"
    +"<linearGradient id='orough"+SUF+"' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#5E6B3C'/><stop offset='1' stop-color='#39492F'/></linearGradient>"
    +"<linearGradient id='owat"+SUF+"' x1='0' y1='0' x2='0.9' y2='1'><stop offset='0' stop-color='#2C4A52'/><stop offset='0.55' stop-color='#1E3A44'/><stop offset='1' stop-color='#152B33'/></linearGradient>"
    +"<radialGradient id='oglow"+SUF+"' cx='0.28' cy='0.2' r='0.95'><stop offset='0' stop-color='#FFE9B0' stop-opacity='0.32'/><stop offset='0.55' stop-color='#FFD98C' stop-opacity='0.10'/><stop offset='1' stop-color='#43333B' stop-opacity='0.30'/></radialGradient>"
    +"</defs>";
  var s="<rect x='-155' y='-565' width='260' height='615' fill='#4A5637'/>";
  // ground: two broad underpainting passes
  s+="<g filter='url(#ob1"+SUF+")'><path d='"+smooth(corridor(0,totalLen,function(a){return safeFw(a)+30;},R),true)+"' fill='url(#orough"+SUF+")'/></g>";
  s+="<g filter='url(#ob2"+SUF+")'><path d='"+smooth(corridor(2,totalLen,function(a){return safeFw(a)+18;},R),true)+"' fill='#4E6238' opacity='0.65'/></g>";
  // fairway: lit from the west, two passes + soft mow bands
  if(G.fwStart!=null){
  var fwD=smooth(corridor(G.fwStart,totalLen-8,safeFw,null),true);
  s+="<g filter='url(#ob2"+SUF+")'><path d='"+fwD+"' fill='url(#ofw"+SUF+")'/></g>";
  s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(corridor(G.fwStart+6,totalLen-14,function(a){return safeFw(a)-3;},null),true)+"' fill='#D8C77E' opacity='0.22'/></g>";
  for(var a=G.fwStart+16; a<totalLen-24; a+=26){
    var q=lineAt(a), pp=[q.d[1],-q.d[0]], w=safeFw(a)-2;
    s+="<g filter='url(#ob3"+SUF+")'><path d='M"+(q.p[0]-pp[0]*w)+","+(q.p[1]-pp[1]*w)+" L"+(q.p[0]+pp[0]*w)+","+(q.p[1]+pp[1]*w)+"' stroke='#F1E3A2' stroke-width='9' opacity='0.055' stroke-linecap='round'/></g>";  }
  }
  // water: deep, with one warm reflection
  G.waters.forEach(function(w,wi){
    var d=smooth(w,true);
    s+="<g filter='url(#ob2"+SUF+")'><path d='"+d+"' fill='url(#owat"+SUF+")'/></g>";
    s+="<g filter='url(#ob2"+SUF+")'><path d='"+d+"' fill='none' stroke='#0E2029' stroke-width='2.4' opacity='0.6'/></g>";
    var c=[0,0]; w.forEach(function(p){c[0]+=p[0];c[1]+=p[1];}); c[0]/=w.length; c[1]/=w.length;
    s+="<g filter='url(#ob3"+SUF+")'><ellipse cx='"+(c[0]-8)+"' cy='"+(c[1]-6)+"' rx='17' ry='5' fill='#F5D98F' opacity='"+(wi===0?0.30:0.22)+"'/></g>";
    s+="<g filter='url(#ob3"+SUF+")'><ellipse cx='"+(c[0]-2)+"' cy='"+(c[1]+2)+"' rx='9' ry='2.6' fill='#C8E0D8' opacity='0.18'/></g>";
  });
  // bunkers: warm cream with a shadowed lip on the east
  G.bunkers.forEach(function(b){
    s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(b,true)+"' fill='#E4CE93'/></g>";
    s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(inset(b.slice(0,-1),0.72),true)+"' fill='none' stroke='#9C7F4E' stroke-width='1.6' opacity='0.5'/></g>";
    s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(b,true)+"' fill='none' stroke='#2E3A26' stroke-width='0.9' opacity='0.4'/></g>";
  });
  // green: luminous
  s+="<g filter='url(#ob2"+SUF+")'><path d='"+smooth(inset(G.green.slice(0,-1),1.25),true)+"' fill='#3E5534' opacity='0.7'/></g>";
  s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(G.green,true)+"' fill='#9DB86A'/></g>";
  s+="<g filter='url(#ob3"+SUF+")'><path d='"+smooth(inset(G.green.slice(0,-1),0.6),true)+"' fill='#C9DA8C' opacity='0.6'/></g>";
  // flag: one red dab + long thin shadow
  var gp=lineAt(totalLen).p;
  s+="<line x1='"+gp[0]+"' y1='"+gp[1]+"' x2='"+(gp[0]+9)+"' y2='"+(gp[1]+2.5)+"' stroke='#20301E' stroke-width='1' opacity='0.5'/>";
  s+="<line x1='"+gp[0]+"' y1='"+gp[1]+"' x2='"+gp[0]+"' y2='"+(gp[1]-12)+"' stroke='#2A241C' stroke-width='1.1'/>";
  s+="<path d='M"+gp[0]+","+(gp[1]-12)+" q5,1.4 7,3.6 q-4,0.6 -7,0.2 z' fill='#B8442E'/>";
  // trees: three-layer crowns, long violet shadows east
  treeSpots(R).forEach(function(t){
    var r=t[2];
    s+="<g filter='url(#ob3"+SUF+")'><ellipse cx='"+(t[0]+r*1.7)+"' cy='"+(t[1]+3)+"' rx='"+(r*1.9)+"' ry='"+(r*0.5)+"' fill='#2F2C3E' opacity='0.38'/></g>";
    s+="<g filter='url(#ob2"+SUF+")'><ellipse cx='"+t[0]+"' cy='"+t[1]+"' rx='"+(r*1.12)+"' ry='"+(r*0.66)+"' fill='#26361F'/></g>";
    s+="<g filter='url(#ob3"+SUF+")'><ellipse cx='"+(t[0]-r*0.18)+"' cy='"+(t[1]-r*0.16)+"' rx='"+(r*0.78)+"' ry='"+(r*0.44)+"' fill='#456030'/></g>";
    s+="<g filter='url(#ob3"+SUF+")'><ellipse cx='"+(t[0]-r*0.38)+"' cy='"+(t[1]-r*0.34)+"' rx='"+(r*0.4)+"' ry='"+(r*0.22)+"' fill='#A8B865' opacity='0.85'/></g>";
  });
  // evening light + vignette over everything
  s+="<rect x='-155' y='-565' width='260' height='615' fill='url(#oglow"+SUF+")'/>";
  // canvas tooth
  s+="<rect x='-155' y='-565' width='260' height='615' filter='url(#ocanvas"+SUF+")' opacity='0.16' style='mix-blend-mode:multiply'/>";
  // painter's marks: a numeral and a signature, nothing else
  s+="<text x='-140' y='36' font-size='26' font-family='Fraunces, Georgia, serif' font-weight='600' fill='#EFE3B4' opacity='0.9'>"+H.hole+"</text>";
  s+="<text x='96' y='38' font-size='14' font-family='Caveat, cursive' font-weight='600' fill='#EFE3B4' opacity='0.85' text-anchor='end'>yoink.</text>";
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s;

}

/* ============================================================
   Six additional painters — Surveyor, Field Note, Instrument,
   Caddie, Fairway, Landform Day. All measured off the pack.
   ============================================================ */
function measureH(H){
  var SEG=[], TOT=0;
  for(var i=0;i<H.line.length-1;i++){ var a=H.line[i],b=H.line[i+1];
    var L=Math.hypot(b[0]-a[0],b[1]-a[1]); SEG.push({a:a,b:b,L:L}); TOT+=L; }
  function proj(p){
    var best=1e9, arc=0, side=1, acc=0;
    for(var i=0;i<SEG.length;i++){
      var s=SEG[i], vx=s.b[0]-s.a[0], vy=s.b[1]-s.a[1];
      var t=Math.max(0,Math.min(1,((p[0]-s.a[0])*vx+(p[1]-s.a[1])*vy)/(s.L*s.L)));
      var qx=s.a[0]+vx*t, qy=s.a[1]+vy*t, d=Math.hypot(p[0]-qx,p[1]-qy);
      if(d<best){ best=d; arc=acc+t*s.L; side=(vx*(p[1]-s.a[1])-vy*(p[0]-s.a[0]))>0?1:-1; }
      acc+=s.L;
    }
    return {arc:arc, side:side};
  }
  function span(poly){ var lo=1e9,hi=-1e9,sd=0;
    poly.forEach(function(p){ var r=proj(p); if(r.arc<lo)lo=r.arc; if(r.arc>hi)hi=r.arc; sd+=r.side; });
    return {lo:Math.round(lo), hi:Math.round(hi), side:sd>=0?1:-1}; }
  var gr=span(H.green), hz=[];
  (H.bunkers||[]).forEach(function(b){ var s=span(b); s.kind='sand'; hz.push(s); });
  (H.waters||[]).forEach(function(w){ var s=span(w); s.kind='water'; hz.push(s); });
  hz.sort(function(a,b){ return a.lo-b.lo; });
  var total=H.total||H.yards.mid;
  var carry=hz.filter(function(h){ return h.lo>70 && h.hi<gr.lo-12; });
  var land=(H.par>3)?Math.round(Math.max(180,Math.min(285,total-155))):null;
  var tee=land?carry.filter(function(h){ return h.lo<land-8; }):[];
  return { front:gr.lo, back:gr.hi, mid:Math.round((gr.lo+gr.hi)/2), total:total,
           carry:carry, teeCarry:(tee.length?tee[tee.length-1]:(carry[0]||null)), land:land };
}
/* squeeze the fitted art into a sub-rectangle of the page */
function artBox(x0,y0,w,h){
  var pts=[]; function eat(a){ (a||[]).forEach(function(p){ pts.push(p); }); }
  eat(G.line); eat(G.green); eat(G.tees);
  (G.bunkers||[]).forEach(eat); (G.waters||[]).forEach(eat);
  var xs=pts.map(function(p){return p[0];}), ys=pts.map(function(p){return p[1];});
  var bx0=Math.min.apply(0,xs)-6, bx1=Math.max.apply(0,xs)+6;
  var by0=Math.min.apply(0,ys)-6, by1=Math.max.apply(0,ys)+4;
  var k=Math.min(w/(bx1-bx0), h/(by1-by0));
  return { t:"translate("+(x0+w/2-k*(bx0+bx1)/2).toFixed(2)+","+(y0+h-k*by1).toFixed(2)+") scale("+k.toFixed(3)+")", k:k };
}

/* ---------------- 1. SURVEYOR ---------------- */
function renderSurveyor(el,H,meta){
  var S=fitPage(H), SUF='_'+el.id, M=measureH(H);
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':survey');
  var INK='#4A3A26', TINT_W='#D8E4E4', TINT_G='#E4E9D8';
  var defs='<defs>'
   +'<filter id="sfox'+SUF+'"><feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="4" seed="3" result="n"/><feColorMatrix in="n" type="matrix" values="0 0 0 0 0.55 0 0 0 0 0.44 0 0 0 0 0.28 0 0 0 0.10 0"/></filter>'
   +'<filter id="snib'+SUF+'"><feTurbulence type="fractalNoise" baseFrequency="0.08" numOctaves="2" seed="13"/><feDisplacementMap in="SourceGraphic" scale="1.8"/></filter>'
   +'<pattern id="shatch'+SUF+'" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(38)"><line x1="0" y1="0" x2="0" y2="4" stroke="'+INK+'" stroke-width="0.55" opacity="0.85"/></pattern>'
   +'<pattern id="swave'+SUF+'" width="9" height="5" patternUnits="userSpaceOnUse"><path d="M0,3 Q2.2,1 4.5,3 T9,3" fill="none" stroke="'+INK+'" stroke-width="0.5" opacity="0.8"/></pattern>'
   +'<pattern id="sstip'+SUF+'" width="6" height="6" patternUnits="userSpaceOnUse"><circle cx="1.4" cy="1.7" r="0.5" fill="'+INK+'" opacity="0.55"/><circle cx="4.3" cy="4.6" r="0.45" fill="'+INK+'" opacity="0.45"/></pattern>'
   +'</defs>';
  var s='<rect x="-155" y="-565" width="260" height="615" fill="#EFE6D0"/>'
       +'<rect x="-155" y="-565" width="260" height="615" filter="url(#sfox'+SUF+')"/>'
       +'<rect x="-149" y="-559" width="248" height="603" fill="none" stroke="'+INK+'" stroke-width="1.4"/>'
       +'<rect x="-146" y="-556" width="242" height="597" fill="none" stroke="'+INK+'" stroke-width="0.5"/>';
  var nib='<g filter="url(#snib'+SUF+')">';
  if(G.fwStart!=null) nib+='<path d="'+smooth(corridor(G.fwStart,totalLen-8,safeFw,R),true)+'" fill="'+TINT_G+'"/>';
  G.waters.forEach(function(w){ nib+='<path d="'+smooth(w,true)+'" fill="'+TINT_W+'"/>'; });
  nib+='<path d="'+smooth(corridor(12,totalLen-4,function(a){return safeFw(a)+22;},R),true)+'" fill="url(#sstip'+SUF+')" opacity="0.5"/>';
  G.waters.forEach(function(w){ var d=smooth(w,true);
    nib+='<path d="'+d+'" fill="url(#swave'+SUF+')"/><path d="'+d+'" fill="none" stroke="'+INK+'" stroke-width="1.1"/>'; });
  if(G.fwStart!=null) nib+='<path d="'+smooth(corridor(G.fwStart,totalLen-8,safeFw,R),true)+'" fill="none" stroke="'+INK+'" stroke-width="0.9" stroke-dasharray="5 2"/>';
  G.bunkers.forEach(function(b){ var d=smooth(b,true);
    nib+='<path d="'+d+'" fill="url(#shatch'+SUF+')"/><path d="'+d+'" fill="none" stroke="'+INK+'" stroke-width="1"/>'; });
  var gd=smooth(G.green,true);
  nib+='<path d="'+gd+'" fill="#E9EDDA"/><path d="'+gd+'" fill="none" stroke="'+INK+'" stroke-width="1.3"/>';
  treeSpots(R).forEach(function(t){
    nib+='<circle cx="'+t[0].toFixed(1)+'" cy="'+t[1].toFixed(1)+'" r="'+(t[2]*0.75).toFixed(1)+'" fill="none" stroke="'+INK+'" stroke-width="0.8"/>';
    nib+='<circle cx="'+(t[0]+3).toFixed(1)+'" cy="'+(t[1]+2).toFixed(1)+'" r="'+(t[2]*0.4).toFixed(1)+'" fill="none" stroke="'+INK+'" stroke-width="0.55"/>';
  });
  nib+='<path d="'+smooth(G.line,false)+'" fill="none" stroke="'+INK+'" stroke-width="0.8" stroke-dasharray="7 3 1.5 3"/>';
  G.tees.forEach(function(t){ nib+='<rect x="'+(t[0]-3).toFixed(1)+'" y="'+(t[1]-2).toFixed(1)+'" width="6" height="4" fill="none" stroke="'+INK+'" stroke-width="0.9"/>'; });
  nib+='</g>';
  s+=nib;
  /* dimension ticks — a survey states its measurements */
  for(var y=100;y<M.front-40;y+=100){
    var q=lineAt(y*S), w=safeFw(y*S)+12, pp=[q.d[1],-q.d[0]];
    var x1=q.p[0]-pp[0]*w, y1=q.p[1]-pp[1]*w, x2=q.p[0]+pp[0]*w, y2=q.p[1]+pp[1]*w;
    s+='<line x1="'+x1.toFixed(1)+'" y1="'+y1.toFixed(1)+'" x2="'+x2.toFixed(1)+'" y2="'+y2.toFixed(1)+'" stroke="'+INK+'" stroke-width="0.5" stroke-dasharray="3 2" opacity="0.75"/>';
    s+='<text x="'+(x2+3).toFixed(1)+'" y="'+(y2+2.4).toFixed(1)+'" font-size="7" font-family="\'IM Fell English\', serif" fill="'+INK+'">'+y+'</text>';
  }
  if(M.teeCarry){
    var h=M.teeCarry, q2=lineAt(((h.lo+h.hi)/2)*S), pp2=[q2.d[1],-q2.d[0]], off=safeFw(((h.lo+h.hi)/2)*S)+16;
    var lx=Math.max(-138,Math.min(88,q2.p[0]+pp2[0]*off*h.side));
    s+='<text x="'+lx.toFixed(1)+'" y="'+(q2.p[1]+2).toFixed(1)+'" font-size="8.5" font-family="\'IM Fell English\', serif" fill="'+INK+'" text-anchor="'+(h.side>0?'start':'end')+'">carry '+h.lo+'</text>';
  }
  var nm=stripName(meta.name||'THE COURSE');
  s+='<g font-family="\'IM Fell English\', serif" fill="'+INK+'" text-anchor="middle">'
   +'<text x="-25" y="-538" font-size="'+Math.max(11,Math.min(19,300/Math.max(1,nm.length))).toFixed(1)+'" letter-spacing="3">'+nm+'</text>'
   +'<text x="-25" y="-522" font-size="10" font-style="italic">Hole '+H.hole+' &#183; '+M.total+' yards &#183; par '+H.par+'</text>'
   +'<text x="60" y="20" font-size="9" font-style="italic" text-anchor="end">Green '+M.front+' front &#183; '+M.back+' back</text></g>'
   +'<g stroke="'+INK+'" fill="'+INK+'"><line x1="-140" y1="24" x2="'+(-140+100*S).toFixed(1)+'" y2="24" stroke-width="1"/>'
   +'<line x1="-140" y1="20" x2="-140" y2="28" stroke-width="1"/><line x1="'+(-140+100*S).toFixed(1)+'" y1="20" x2="'+(-140+100*S).toFixed(1)+'" y2="28" stroke-width="1"/>'
   +'<text x="'+(-140+50*S).toFixed(1)+'" y="40" font-size="9" font-family="\'IM Fell English\', serif" text-anchor="middle" stroke="none">100 yards</text>'
   +'<g transform="translate(75,-460)"><line x1="0" y1="14" x2="0" y2="-14" stroke-width="1"/><path d="M0,-14 L-3.5,-5 L0,-8 L3.5,-5 Z" stroke="none"/><text x="0" y="-18" font-size="10" font-family="\'IM Fell English\', serif" text-anchor="middle" stroke="none">N</text></g></g>';
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s;
}

/* ---------------- 2. FIELD NOTE ---------------- */
function renderFieldNote(el,H,meta){
  var S=fitPage(H), SUF='_'+el.id, M=measureH(H);
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':field');
  var G1='#8A8A82', G2='#5E5E57', G3='#3C3C37', RED='#C6392B', PAPER='#F6F4EC';
  var defs='<defs>'
   +'<filter id="fwob'+SUF+'"><feTurbulence type="fractalNoise" baseFrequency="0.05" numOctaves="2" seed="29"/><feDisplacementMap in="SourceGraphic" scale="2.6"/></filter>'
   +'<filter id="fwax'+SUF+'"><feTurbulence type="fractalNoise" baseFrequency="0.11" numOctaves="2" seed="37"/><feDisplacementMap in="SourceGraphic" scale="2"/></filter>'
   +'<pattern id="fx1'+SUF+'" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(24)"><line x1="0" y1="0" x2="0" y2="5" stroke="'+G1+'" stroke-width="0.5"/></pattern>'
   +'<pattern id="fx2'+SUF+'" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(-33)"><line x1="0" y1="0" x2="0" y2="4" stroke="'+G2+'" stroke-width="0.5"/></pattern>'
   +'<pattern id="fscrib'+SUF+'" width="7" height="4" patternUnits="userSpaceOnUse"><path d="M0,2 Q1.7,0 3.5,2 T7,2" fill="none" stroke="'+G3+'" stroke-width="0.55"/></pattern>'
   +'<filter id="ftooth'+SUF+'"><feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="2" seed="2" result="n"/><feColorMatrix in="n" type="matrix" values="0 0 0 0 0.4 0 0 0 0 0.4 0 0 0 0 0.38 0 0 0 0.04 0"/></filter>'
   +'</defs>';
  var s='<rect x="-155" y="-565" width="260" height="615" fill="'+PAPER+'"/>'
       +'<rect x="-155" y="-565" width="260" height="615" filter="url(#ftooth'+SUF+')"/>';
  var g='<g filter="url(#fwob'+SUF+')">';
  g+='<path d="'+smooth(corridor(12,totalLen-4,function(a){return safeFw(a)+22;},R),true)+'" fill="url(#fx1'+SUF+')" opacity="0.55"/>';
  if(G.fwStart!=null){
    var fwd=smooth(corridor(G.fwStart,totalLen-8,safeFw,R),true);
    g+='<path d="'+fwd+'" fill="'+PAPER+'"/><path d="'+fwd+'" fill="none" stroke="'+G2+'" stroke-width="1"/>';
  }
  G.waters.forEach(function(w){ var d=smooth(w,true);
    g+='<path d="'+d+'" fill="url(#fx1'+SUF+')"/><path d="'+d+'" fill="url(#fx2'+SUF+')"/><path d="'+d+'" fill="none" stroke="'+G3+'" stroke-width="1.1"/>'; });
  G.bunkers.forEach(function(b){ var d=smooth(b,true);
    g+='<path d="'+d+'" fill="url(#fscrib'+SUF+')"/><path d="'+d+'" fill="none" stroke="'+G2+'" stroke-width="0.9"/>'; });
  var gd=smooth(G.green,true);
  g+='<path d="'+gd+'" fill="none" stroke="'+G3+'" stroke-width="1.3"/>';
  g+='<path d="'+gd+'" fill="none" stroke="'+G1+'" stroke-width="0.6" transform="translate(-0.4,2) scale(0.96)" opacity="0.8"/>';
  treeSpots(R).forEach(function(t){
    g+='<path d="'+smooth([[t[0]-t[2],t[1]],[t[0]-t[2]*0.3,t[1]-t[2]*0.9],[t[0]+t[2]*0.5,t[1]-t[2]*0.7],[t[0]+t[2],t[1]+2],[t[0],t[1]+t[2]*0.4]],true)+'" fill="none" stroke="'+G2+'" stroke-width="0.8"/>';
  });
  g+='</g>';
  s+=g;
  /* the caddie's own red pencil, over the top */
  var red='<g filter="url(#fwax'+SUF+')" stroke="'+RED+'" fill="none" stroke-linecap="round">';
  red+='<path d="'+smooth(G.line,false)+'" stroke-width="2.4" opacity="0.9"/>';
  var notes=[];
  if(M.land!=null){
    var lq=lineAt(M.land*S);
    red+='<circle cx="'+lq.p[0].toFixed(1)+'" cy="'+lq.p[1].toFixed(1)+'" r="12" stroke-width="1.6"/>';
    notes.push([lq.p[0], lq.p[1]+5, ''+M.land, 'middle', 14]);
    notes.push([lq.p[0]+17, lq.p[1]+18, 'leaves '+(M.total-M.land), 'start', 12]);
  }
  if(M.teeCarry){
    var h=M.teeCarry, q=lineAt(h.lo*S), pp=[q.d[1],-q.d[0]], off=safeFw(h.lo*S)+14;
    var ax=q.p[0]+pp[0]*off*h.side, ay=q.p[1]+pp[1]*off*h.side;
    red+='<path d="M'+ax.toFixed(1)+','+ay.toFixed(1)+' L'+(q.p[0]+pp[0]*8*h.side).toFixed(1)+','+q.p[1].toFixed(1)+'" stroke-width="1.4"/>';
    notes.push([ax+(h.side>0?3:-3), ay+4, 'carry '+h.lo, h.side>0?'start':'end', 13]);
  }
  red+='</g>';
  red+='<g font-family="Caveat, cursive" fill="'+RED+'" font-weight="600">';
  notes.forEach(function(n){ red+='<text x="'+n[0].toFixed(1)+'" y="'+n[1].toFixed(1)+'" font-size="'+n[4]+'" text-anchor="'+n[3]+'">'+n[2]+'</text>'; });
  if(H.sign) red+='<text x="-148" y="-52" font-size="13">'+H.sign+'</text>';
  red+='</g>';
  s+=red;
  var nm=stripName(meta.name||'THE COURSE');
  s+='<g font-family="Archivo, sans-serif" fill="'+G3+'">'
   +'<text x="-146" y="-536" font-size="'+Math.max(10,Math.min(17,235/Math.max(1,nm.length+4))).toFixed(1)+'" font-weight="700" letter-spacing="2">'+nm+' &#8212; '+H.hole+'</text>'
   +'<text x="-146" y="-518" font-size="11" fill="'+G2+'" letter-spacing="1">PAR '+H.par+' &#183; '+M.total+' &#183; GREEN '+M.front+'/'+M.back+'</text>'
   +'<line x1="-146" y1="-510" x2="96" y2="-510" stroke="'+G1+'" stroke-width="0.7"/></g>';
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s;
}

/* ---------------- 3. INSTRUMENT ---------------- */
function renderInstrument(el,H,meta){
  var S=fitPage(H), SUF='_'+el.id, M=measureH(H);
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':instr');
  var FIELD='#06090A', PANEL='#0D1214', W='#FFFFFF', ACID='#C7F24A';
  var defs="<defs>"
    +"<filter id='inglow"+SUF+"' x='-70%' y='-70%' width='240%' height='240%'><feGaussianBlur stdDeviation='2' result='b'/><feMerge><feMergeNode in='b'/><feMergeNode in='SourceGraphic'/></feMerge></filter>"
    +"<pattern id='inwat"+SUF+"' width='6' height='6' patternUnits='userSpaceOnUse' patternTransform='rotate(38)'><line x1='0' y1='0' x2='0' y2='6' stroke='"+W+"' stroke-width='0.7' opacity='0.30'/></pattern>"
    +"<pattern id='insand"+SUF+"' width='4.4' height='4.4' patternUnits='userSpaceOnUse'><circle cx='1.1' cy='1.2' r='0.55' fill='"+W+"' opacity='0.42'/><circle cx='3.3' cy='3.4' r='0.45' fill='"+W+"' opacity='0.3'/></pattern>"
    +"</defs>";
  var you=(H.par>3)?Math.round(M.total*0.58):0;
  var toGo=M.mid-you;
  var s="<rect x='-155' y='-565' width='260' height='615' fill='"+FIELD+"'/>";
  s+="<rect x='-155' y='-565' width='260' height='72' fill='"+PANEL+"'/>";
  s+="<line x1='-155' y1='-493' x2='105' y2='-493' stroke='"+W+"' stroke-width='0.8' opacity='0.32'/>";
  s+="<g font-family='Archivo, sans-serif'>";
  s+="<text x='-140' y='-540' font-size='6.5' font-weight='800' letter-spacing='2.6' fill='"+W+"' opacity='0.5'>TO CENTRE</text>";
  s+="<text x='-142' y='-508' font-size='40' font-weight='900' fill='"+ACID+"' filter='url(#inglow"+SUF+")'>"+toGo+"</text>";
  s+="<text x='-46' y='-518' font-size='7' font-weight='800' letter-spacing='1.4' fill='"+W+"' opacity='0.45'>FRONT</text>";
  s+="<text x='-46' y='-506' font-size='13' font-weight='900' fill='"+W+"' opacity='0.92'>"+(M.front-you)+"</text>";
  s+="<text x='-2' y='-518' font-size='7' font-weight='800' letter-spacing='1.4' fill='"+W+"' opacity='0.45'>BACK</text>";
  s+="<text x='-2' y='-506' font-size='13' font-weight='900' fill='"+W+"' opacity='0.92'>"+(M.back-you)+"</text>";
  s+="<text x='96' y='-540' font-size='6.5' font-weight='800' letter-spacing='2' fill='"+W+"' opacity='0.5' text-anchor='end'>HOLE "+H.hole+" &#183; PAR "+H.par+"</text>";
  s+="<text x='96' y='-518' font-size='7' font-weight='800' letter-spacing='1.4' fill='"+W+"' opacity='0.45' text-anchor='end'>PLAYS</text>";
  s+="<text x='96' y='-506' font-size='13' font-weight='900' fill='"+W+"' opacity='0.92' text-anchor='end'>"+M.total+"</text>";
  s+="</g>";
  var B=artBox(-138,-486,216,466);
  s+="<g transform='"+B.t+"' stroke-width='1' vector-effect='non-scaling-stroke'>";
  s+="<path d='"+smooth(corridor(6,totalLen,function(a){return safeFw(a)+20;},R),true)+"' fill='none' stroke='"+W+"' stroke-width='0.6' opacity='0.20'/>";
  if(G.fwStart!=null)
    s+="<path d='"+smooth(corridor(G.fwStart,totalLen-8,safeFw,null),true)+"' fill='"+W+"' fill-opacity='0.085' stroke='"+W+"' stroke-width='0.9' opacity='0.6'/>";
  G.waters.forEach(function(w){ var d=smooth(w,true);
    s+="<path d='"+d+"' fill='url(#inwat"+SUF+")'/><path d='"+d+"' fill='none' stroke='"+W+"' stroke-width='1.1' opacity='0.75'/>"; });
  G.bunkers.forEach(function(b){ var d=smooth(b,true);
    s+="<path d='"+d+"' fill='url(#insand"+SUF+")'/><path d='"+d+"' fill='none' stroke='"+W+"' stroke-width='0.7' opacity='0.5'/>"; });
  treeSpots(R).forEach(function(t){
    s+="<ellipse cx='"+t[0].toFixed(1)+"' cy='"+t[1].toFixed(1)+"' rx='"+(t[2]*1.02).toFixed(1)+"' ry='"+(t[2]*0.56).toFixed(1)+"' fill='none' stroke='"+W+"' stroke-width='0.6' opacity='0.28'/>"; });
  G.tees.forEach(function(t){ s+="<rect x='"+(t[0]-3.6).toFixed(1)+"' y='"+(t[1]-2).toFixed(1)+"' width='7.2' height='4' fill='none' stroke='"+W+"' stroke-width='0.8' opacity='0.5'/>"; });
  s+="<path d='"+smooth(G.green,true)+"' fill='"+W+"' fill-opacity='0.13' stroke='"+W+"' stroke-width='1.3' opacity='0.95'/>";
  s+="<path d='"+smooth(G.line,false)+"' fill='none' stroke='"+W+"' stroke-width='1.3' stroke-dasharray='7 5' opacity='0.35'/>";
  var ahead=[], a0=you*S;
  for(var a=a0;a<=totalLen;a+=Math.max(3,totalLen/60)) ahead.push(lineAt(a).p);
  ahead.push(lineAt(totalLen).p);
  if(ahead.length>1) s+="<path d='"+smooth(ahead,false)+"' fill='none' stroke='"+ACID+"' stroke-width='1.8' stroke-linecap='round'/>";
  var gp=lineAt(totalLen).p, me=lineAt(a0).p;
  s+="<circle cx='"+gp[0].toFixed(1)+"' cy='"+gp[1].toFixed(1)+"' r='2.4' fill='"+ACID+"' filter='url(#inglow"+SUF+")'/>";
  s+="<circle cx='"+me[0].toFixed(1)+"' cy='"+me[1].toFixed(1)+"' r='3.4' fill='"+ACID+"' filter='url(#inglow"+SUF+")'/>";
  s+="<circle cx='"+me[0].toFixed(1)+"' cy='"+me[1].toFixed(1)+"' r='8.5' fill='none' stroke='"+ACID+"' stroke-width='0.7' opacity='0.4'/>";
  function tick(yds,label){
    var q=lineAt(yds*S), w=safeFw(yds*S)+8, pp=[q.d[1],-q.d[0]];
    var x1=q.p[0]-pp[0]*w, y1=q.p[1]-pp[1]*w, x2=q.p[0]+pp[0]*w, y2=q.p[1]+pp[1]*w;
    var lx=Math.max(x1,x2)+5, ly=(x1>x2?y1:y2)+2.6;
    return "<line x1='"+x1.toFixed(1)+"' y1='"+y1.toFixed(1)+"' x2='"+x2.toFixed(1)+"' y2='"+y2.toFixed(1)+"' stroke='"+W+"' stroke-width='0.7' stroke-dasharray='2 2' opacity='0.55'/>"
      +"<text x='"+lx.toFixed(1)+"' y='"+ly.toFixed(1)+"' font-size='7.6' font-family='Archivo, sans-serif' font-weight='800' fill='"+W+"' opacity='0.85'>"+label+"</text>";
  }
  if(H.fw_start) s+=tick(H.fw_start, H.fw_start);
  if(H.bend && H.bend.at) s+=tick(H.bend.at, H.bend.at);
  s+="</g>";
  if(M.teeCarry) s+="<text x='96' y='-56' font-size='7' font-family='Archivo, sans-serif' font-weight='800' fill='"+W+"' opacity='0.7' text-anchor='end'>CARRY "+M.teeCarry.lo+" &#183; "+(M.teeCarry.kind==='water'?'WATER':'SAND')+"</text>";
  s+="<rect x='-155' y='6' width='260' height='44' fill='"+PANEL+"'/>";
  s+="<line x1='-155' y1='6' x2='105' y2='6' stroke='"+W+"' stroke-width='0.8' opacity='0.32'/>";
  s+="<g font-family='Archivo, sans-serif'>";
  s+="<text x='-140' y='22' font-size='6.5' font-weight='800' letter-spacing='2' fill='"+W+"' opacity='0.45'>THE GREEN</text>";
  s+="<text x='-140' y='36' font-size='10' font-weight='900' fill='"+W+"' opacity='0.92'>"+M.front+" FRONT &#183; "+M.back+" BACK &#183; "+(H.depth||'?')+" DEEP</text>";
  s+="<text x='96' y='22' font-size='6.5' font-weight='800' letter-spacing='2' fill='"+W+"' opacity='0.45' text-anchor='end'>YOINK</text>";
  s+="<text x='96' y='36' font-size='9' font-weight='800' fill='"+ACID+"' text-anchor='end'>INSTRUMENT</text>";
  s+="</g>";
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s;
}

/* ---------------- 4. CADDIE (dark board) ---------------- */
function renderCaddie(el,H,meta){
  var S=fitPage(H), SUF='_'+el.id, M=measureH(H);
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':caddie');
  var ACID='#C7F24A', PINE='#14432A', DEEP='#0B2318', CREAM='#F6F4EB', MUT='#7E9B7E';
  var FA="font-family='Archivo, sans-serif'";
  var nm=stripName(meta.name||'THE COURSE');
  var s="<rect x='-155' y='-565' width='260' height='615' fill='"+DEEP+"'/>";
  s+="<text x='-136' y='-535' font-size='7.4' "+FA+" font-weight='800' letter-spacing='0.18em' fill='"+MUT+"'>"+nm+"</text>";
  s+="<text x='-136' y='-515' font-size='19' "+FA+" font-weight='900' letter-spacing='-0.03em' fill='"+CREAM+"'>Hole "+H.hole+"</text>";
  s+="<text x='86' y='-528' font-size='7.4' "+FA+" font-weight='800' letter-spacing='0.14em' fill='"+MUT+"' text-anchor='end'>PAR "+H.par+"</text>";
  s+="<text x='86' y='-515' font-size='11' "+FA+" font-weight='900' fill='"+CREAM+"' text-anchor='end'>"+M.total+" YDS</text>";
  s+="<text x='-138' y='-470' font-size='58' "+FA+" font-weight='900' letter-spacing='-0.05em' fill='"+ACID+"'>"+M.mid+"</text>";
  s+="<text x='-42' y='-478' font-size='7.4' "+FA+" font-weight='800' letter-spacing='0.14em' fill='"+MUT+"'>TO CENTRE</text>";
  var cols=[['FRONT',M.front,0],['CENTRE',M.mid,1],['BACK',M.back,0]], x=-136, w=74;
  cols.forEach(function(c,i){
    var cx=x+i*(w+4);
    s+="<rect x='"+cx+"' y='-462' width='"+w+"' height='27' rx='6' fill='"+(c[2]?ACID:'none')+"' stroke='"+(c[2]?ACID:'rgba(199,242,74,0.3)')+"' stroke-width='1'/>";
    s+="<text x='"+(cx+8)+"' y='-450' font-size='5.8' "+FA+" font-weight='800' letter-spacing='0.14em' fill='"+(c[2]?'rgba(20,67,42,0.72)':MUT)+"'>"+c[0]+"</text>";
    s+="<text x='"+(cx+8)+"' y='-440' font-size='13' "+FA+" font-weight='900' letter-spacing='-0.02em' fill='"+(c[2]?PINE:CREAM)+"'>"+c[1]+"</text>";
  });
  s+="<rect x='-140' y='-426' width='232' height='406' rx='14' fill='rgba(199,242,74,0.045)'/>";
  var B=artBox(-136,-422,224,398);
  s+="<g transform='"+B.t+"' vector-effect='non-scaling-stroke'>";
  s+="<path d='"+smooth(corridor(6,totalLen-3,function(a){return safeFw(a)+13;},null),true)+"' fill='rgba(199,242,74,0.05)'/>";
  treeSpots(R).forEach(function(t){
    s+="<ellipse cx='"+t[0].toFixed(1)+"' cy='"+t[1].toFixed(1)+"' rx='"+(t[2]*1.02).toFixed(1)+"' ry='"+(t[2]*0.8).toFixed(1)+"' fill='rgba(199,242,74,0.12)' stroke='rgba(246,244,235,0.5)' stroke-width='0.9'/>"; });
  if(G.fwStart!=null)
    s+="<path d='"+smooth(corridor(G.fwStart,totalLen-7,safeFw,null),true)+"' fill='rgba(199,242,74,0.11)' stroke='"+ACID+"' stroke-width='0.9' stroke-opacity='0.75'/>";
  G.waters.forEach(function(w){ s+="<path d='"+smooth(w,true)+"' fill='rgba(246,244,235,0.14)' stroke='"+CREAM+"' stroke-width='1' stroke-opacity='0.85'/>"; });
  G.bunkers.forEach(function(b){ s+="<path d='"+smooth(b,true)+"' fill='none' stroke='"+CREAM+"' stroke-width='1' stroke-opacity='0.8' stroke-dasharray='2.4 1.8'/>"; });
  for(var y=100;y<M.front-40;y+=50){
    var q=lineAt(y*S), ww=safeFw(y*S)+7, pp=[q.d[1],-q.d[0]];
    s+="<line x1='"+(q.p[0]-pp[0]*ww).toFixed(1)+"' y1='"+(q.p[1]-pp[1]*ww).toFixed(1)+"' x2='"+(q.p[0]+pp[0]*ww).toFixed(1)+"' y2='"+(q.p[1]+pp[1]*ww).toFixed(1)+"' stroke='rgba(199,242,74,0.3)' stroke-width='0.6'/>";
    if(y%100===0) s+="<text x='"+(q.p[0]-pp[0]*ww-3).toFixed(1)+"' y='"+(q.p[1]-pp[1]*ww+2.3).toFixed(1)+"' font-size='6.4' "+FA+" font-weight='800' fill='rgba(199,242,74,0.45)' text-anchor='end'>"+y+"</text>";
  }
  s+="<path d='"+smooth(G.green,true)+"' fill='"+ACID+"'/>";
  G.tees.forEach(function(t){ s+="<rect x='"+(t[0]-2.6).toFixed(1)+"' y='"+(t[1]-1.6).toFixed(1)+"' width='5.2' height='3.2' fill='"+CREAM+"'/>"; });
  s+="<path d='"+smooth(G.line,false)+"' fill='none' stroke='"+CREAM+"' stroke-width='0.9' stroke-opacity='0.8' stroke-dasharray='5 4'/>";
  if(M.land!=null){ var lq=lineAt(M.land*S);
    s+="<circle cx='"+lq.p[0].toFixed(1)+"' cy='"+lq.p[1].toFixed(1)+"' r='11' fill='none' stroke='"+ACID+"' stroke-width='1.3' stroke-dasharray='4 3'/>";
    s+="<circle cx='"+lq.p[0].toFixed(1)+"' cy='"+lq.p[1].toFixed(1)+"' r='1.8' fill='"+ACID+"'/>"; }
  var gc=[0,0]; G.green.forEach(function(p){gc[0]+=p[0];gc[1]+=p[1];});
  s+="<circle cx='"+(gc[0]/G.green.length).toFixed(1)+"' cy='"+(gc[1]/G.green.length).toFixed(1)+"' r='2.6' fill='"+DEEP+"'/>";
  s+="</g>";
  var chips=[];
  if(M.teeCarry) chips.push(['CARRY '+M.teeCarry.lo,1]);
  if(M.land!=null) chips.push(['LEAVES '+(M.total-M.land),0]);
  chips.push([(H.depth?H.depth+' DEEP':'PAR '+H.par),0]);
  var cx2=-136;
  chips.forEach(function(c){
    var cw=c[0].length*4.2+16;
    s+="<rect x='"+cx2+"' y='-8' width='"+cw+"' height='19' rx='9.5' fill='"+(c[1]?ACID:'none')+"' stroke='"+(c[1]?ACID:'rgba(246,244,235,0.25)')+"' stroke-width='1'/>";
    s+="<text x='"+(cx2+cw/2)+"' y='4.6' font-size='7' "+FA+" font-weight='800' letter-spacing='0.1em' fill='"+(c[1]?PINE:'#B9CDB2')+"' text-anchor='middle'>"+c[0]+"</text>";
    cx2+=cw+6;
  });
  s+="<g transform='translate(78,26) scale(0.1)'><path d='M50,5 c4.4,0 7.3,3.4 6.9,7.7 L52.7,103 h-5.4 L43.1,12.7 C42.7,8.4 45.6,5 50,5 Z' fill='"+CREAM+"'/><path d='M56.6,11 l31,9.6 -31,9.6 z' fill='"+ACID+"'/><circle cx='50' cy='125.5' r='9.6' fill='"+CREAM+"'/></g>";
  s+="<text x='-136' y='34' font-size='6.2' "+FA+" font-weight='800' letter-spacing='0.14em' fill='#5F7A66'>CADDIE &#183; IN-ROUND</text>";
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=s;
}

/* ---------------- 5. FAIRWAY (light cards) ---------------- */
function renderFairway(el,H,meta){
  var S=fitPage(H), SUF='_'+el.id, M=measureH(H);
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':fairway');
  var ACID='#C7F24A', PINE='#14432A', CREAM='#F6F4EB', MUT='#5F7A66';
  var FA="font-family='Archivo, sans-serif'";
  var nm=stripName(meta.name||'THE COURSE');
  var s="<rect x='-155' y='-565' width='260' height='615' fill='"+CREAM+"'/>";
  s+="<text x='-136' y='-535' font-size='7.4' "+FA+" font-weight='800' letter-spacing='0.18em' fill='"+MUT+"'>"+nm+"</text>";
  s+="<text x='-136' y='-514' font-size='20' "+FA+" font-weight='900' letter-spacing='-0.035em' fill='"+PINE+"'>Hole "+H.hole+" &#183; Par "+H.par+"</text>";
  s+="<text x='86' y='-514' font-size='24' "+FA+" font-weight='900' letter-spacing='-0.04em' fill='"+PINE+"' text-anchor='end'>"+M.total+"</text>";
  s+="<text x='86' y='-503' font-size='6.2' "+FA+" font-weight='800' letter-spacing='0.14em' fill='"+MUT+"' text-anchor='end'>YARDS</text>";
  s+="<rect x='-140' y='-492' width='232' height='412' rx='13' fill='#FFFFFF' stroke='rgba(20,67,42,0.14)' stroke-width='1'/>";
  s+="<rect x='-132' y='-484' width='216' height='340' rx='9' fill='#F3F3E9'/>";
  var B=artBox(-130,-482,212,336);
  s+="<g transform='"+B.t+"' vector-effect='non-scaling-stroke'>";
  s+="<path d='"+smooth(corridor(6,totalLen-3,function(a){return safeFw(a)+13;},null),true)+"' fill='#E8E8D8'/>";
  treeSpots(R).forEach(function(t){
    s+="<path d='M"+t[0].toFixed(1)+","+(t[1]+t[2]*0.5).toFixed(1)+" L"+t[0].toFixed(1)+","+(t[1]+t[2]*1.15).toFixed(1)+"' stroke='"+PINE+"' stroke-width='0.9' stroke-linecap='round'/>";
    s+="<ellipse cx='"+t[0].toFixed(1)+"' cy='"+t[1].toFixed(1)+"' rx='"+(t[2]*1.02).toFixed(1)+"' ry='"+(t[2]*0.8).toFixed(1)+"' fill='#CFDDB6' stroke='"+PINE+"' stroke-width='0.85'/>"; });
  if(G.fwStart!=null)
    s+="<path d='"+smooth(corridor(G.fwStart,totalLen-7,safeFw,null),true)+"' fill='#D8E3C4' stroke='"+PINE+"' stroke-width='1'/>";
  G.waters.forEach(function(w){ s+="<path d='"+smooth(w,true)+"' fill='#DCE7E4' stroke='"+PINE+"' stroke-width='1'/>"; });
  G.bunkers.forEach(function(b){ s+="<path d='"+smooth(b,true)+"' fill='#EFE7CF' stroke='"+PINE+"' stroke-width='1'/>"; });
  for(var y=100;y<M.front-40;y+=50){
    var q=lineAt(y*S), ww=safeFw(y*S)+7, pp=[q.d[1],-q.d[0]];
    s+="<line x1='"+(q.p[0]-pp[0]*ww).toFixed(1)+"' y1='"+(q.p[1]-pp[1]*ww).toFixed(1)+"' x2='"+(q.p[0]+pp[0]*ww).toFixed(1)+"' y2='"+(q.p[1]+pp[1]*ww).toFixed(1)+"' stroke='rgba(20,67,42,0.28)' stroke-width='0.6'/>";
    if(y%100===0) s+="<text x='"+(q.p[0]-pp[0]*ww-3).toFixed(1)+"' y='"+(q.p[1]-pp[1]*ww+2.3).toFixed(1)+"' font-size='6.4' "+FA+" font-weight='800' fill='"+MUT+"' text-anchor='end'>"+y+"</text>";
  }
  s+="<path d='"+smooth(G.green,true)+"' fill='"+ACID+"' stroke='"+PINE+"' stroke-width='1.4'/>";
  G.tees.forEach(function(t){ s+="<rect x='"+(t[0]-2.6).toFixed(1)+"' y='"+(t[1]-1.6).toFixed(1)+"' width='5.2' height='3.2' fill='"+PINE+"'/>"; });
  s+="<path d='"+smooth(G.line,false)+"' fill='none' stroke='"+PINE+"' stroke-width='0.9' stroke-dasharray='5 4'/>";
  if(M.land!=null){ var lq=lineAt(M.land*S);
    s+="<circle cx='"+lq.p[0].toFixed(1)+"' cy='"+lq.p[1].toFixed(1)+"' r='11' fill='none' stroke='"+PINE+"' stroke-width='1.3' stroke-dasharray='4 3'/>";
    s+="<circle cx='"+lq.p[0].toFixed(1)+"' cy='"+lq.p[1].toFixed(1)+"' r='1.8' fill='"+PINE+"'/>"; }
  var gc=[0,0]; G.green.forEach(function(p){gc[0]+=p[0];gc[1]+=p[1];});
  s+="<circle cx='"+(gc[0]/G.green.length).toFixed(1)+"' cy='"+(gc[1]/G.green.length).toFixed(1)+"' r='2.4' fill='"+PINE+"'/>";
  s+="</g>";
  var cols=[['FRONT',M.front],['CENTRE',M.mid],['BACK',M.back],['DEPTH',(H.depth||'—')]];
  cols.forEach(function(c,i){
    var cx=-128+i*54;
    s+="<text x='"+cx+"' y='-128' font-size='5.8' "+FA+" font-weight='800' letter-spacing='0.13em' fill='"+MUT+"'>"+c[0]+"</text>";
    s+="<text x='"+cx+"' y='-112' font-size='16' "+FA+" font-weight='900' letter-spacing='-0.03em' fill='"+PINE+"'>"+c[1]+"</text>";
  });
  if(M.land!=null){
    s+="<rect x='-140' y='-70' width='232' height='46' rx='13' fill='#FFFFFF' stroke='rgba(20,67,42,0.14)' stroke-width='1'/>";
    s+="<text x='-128' y='-54' font-size='6' "+FA+" font-weight='800' letter-spacing='0.13em' fill='"+MUT+"'>WHERE TO LAND IT</text>";
    s+="<text x='-128' y='-34' font-size='21' "+FA+" font-weight='900' letter-spacing='-0.035em' fill='"+PINE+"'>"+M.land+"<tspan font-size='8' font-weight='700' fill='"+MUT+"'> off the tee</tspan></text>";
    var pw=62;
    s+="<rect x='"+(80-pw)+"' y='-62' width='"+pw+"' height='17' rx='8.5' fill='"+ACID+"'/>";
    s+="<text x='"+(80-pw/2)+"' y='-50.6' font-size='7' "+FA+" font-weight='900' letter-spacing='0.09em' fill='"+PINE+"' text-anchor='middle'>LEAVES "+(M.total-M.land)+"</text>";
  } else {
    s+="<rect x='-140' y='-70' width='232' height='46' rx='13' fill='#FFFFFF' stroke='rgba(20,67,42,0.14)' stroke-width='1'/>";
    s+="<text x='-128' y='-54' font-size='6' "+FA+" font-weight='800' letter-spacing='0.13em' fill='"+MUT+"'>ONE SHOT</text>";
    s+="<text x='-128' y='-34' font-size='21' "+FA+" font-weight='900' letter-spacing='-0.035em' fill='"+PINE+"'>"+M.mid+"<tspan font-size='8' font-weight='700' fill='"+MUT+"'> to centre</tspan></text>";
  }
  var list=M.carry.filter(function(h){ return M.land==null || h.lo<M.land+30; }).slice(0,3);
  var bh=15+list.length*13;
  s+="<rect x='-140' y='-18' width='232' height='"+bh+"' rx='13' fill='#FFFFFF' stroke='rgba(20,67,42,0.14)' stroke-width='1'/>";
  s+="<text x='-128' y='-5' font-size='6' "+FA+" font-weight='800' letter-spacing='0.13em' fill='"+MUT+"'>"+(list.length?'CARRIES FROM THE TEE':'NO FORCED CARRY')+"</text>";
  list.forEach(function(h,i){
    var y=8+i*13;
    s+="<text x='-128' y='"+y+"' font-size='8' "+FA+" font-weight='700' fill='"+PINE+"'>"+(h.kind==='water'?'Water ':'Sand ')+(h.side>0?'right':'left')+"</text>";
    s+="<text x='80' y='"+y+"' font-size='9' "+FA+" font-weight='900' fill='"+PINE+"' text-anchor='end'>"+h.lo+"<tspan font-weight='700' fill='"+MUT+"'> / clear "+h.hi+"</tspan></text>";
  });
  s+="<g transform='translate(78,50) scale(0.09)'><path d='M50,5 c4.4,0 7.3,3.4 6.9,7.7 L52.7,103 h-5.4 L43.1,12.7 C42.7,8.4 45.6,5 50,5 Z' fill='"+PINE+"'/><path d='M56.6,11 l31,9.6 -31,9.6 z' fill='"+ACID+"'/><circle cx='50' cy='125.5' r='9.6' fill='"+PINE+"'/></g>";
  s+="<text x='-136' y='50' font-size='6.2' "+FA+" font-weight='800' letter-spacing='0.14em' fill='"+MUT+"'>FAIRWAY &#183; THE APP</text>";
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=s;
}

/* ---------------- 6. LANDFORM DAY ---------------- */
function lfMarksGen(H,S,C){
  var M=measureH(H), s='', FA="font-family='Archivo, sans-serif'";
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  for(var y=200;y<=Math.floor((M.front-40)/50)*50;y+=50){
    var q=lineAt(y*S), w=safeFw(y*S)+(y%100===0?15:9), pp=[q.d[1],-q.d[0]];
    var x1=q.p[0]-pp[0]*w, y1=q.p[1]-pp[1]*w, x2=q.p[0]+pp[0]*w, y2=q.p[1]+pp[1]*w;
    s+="<line x1='"+x1.toFixed(1)+"' y1='"+y1.toFixed(1)+"' x2='"+x2.toFixed(1)+"' y2='"+y2.toFixed(1)+"' stroke='"+C.rule+"' stroke-width='"+(y%100===0?0.8:0.55)+"'"+(y%100===0?"":" stroke-dasharray='2 2.6'")+"/>";
    if(y%100===0) s+="<text x='"+(x1-3.5).toFixed(1)+"' y='"+(y1+2.6).toFixed(1)+"' font-size='7' "+FA+" font-weight='700' letter-spacing='0.12em' fill='"+C.text+"' text-anchor='end'>"+y+"</text>";
  }
  if(M.land!=null){
    var lq=lineAt(M.land*S);
    s+="<circle cx='"+lq.p[0].toFixed(1)+"' cy='"+lq.p[1].toFixed(1)+"' r='12' fill='none' stroke='"+C.acc+"' stroke-width='1.2' stroke-dasharray='4 3'/>";
    s+="<circle cx='"+lq.p[0].toFixed(1)+"' cy='"+lq.p[1].toFixed(1)+"' r='1.8' fill='"+C.acc+"'/>";
    var lbx=Math.min(76,lq.p[0]+16);
    s+="<text x='"+lbx.toFixed(1)+"' y='"+(lq.p[1]-1).toFixed(1)+"' font-size='9.5' "+FA+" font-weight='900' fill='"+C.acc+"'>"+M.land+"</text>";
    s+="<text x='"+lbx.toFixed(1)+"' y='"+(lq.p[1]+7).toFixed(1)+"' font-size='5.6' "+FA+" font-weight='700' letter-spacing='0.12em' fill='"+C.muted+"'>LEAVES "+(M.total-M.land)+"</text>";
  }
  if(M.teeCarry){
    var h=M.teeCarry, q=lineAt(((h.lo+h.hi)/2)*S), pp2=[q.d[1],-q.d[0]], off=safeFw(((h.lo+h.hi)/2)*S)+13;
    var lx=q.p[0]+pp2[0]*off*h.side, ly=q.p[1]+pp2[1]*off*h.side;
    if(M.land!=null){ var lyd=lineAt(M.land*S).p[1];
      if(Math.abs(ly-lyd)<17) ly = lyd + (ly>=lyd?19:-19); }
    lx=Math.max(-128,Math.min(84,lx));
    var anc=h.side>0?'start':'end', dx=h.side>0?4:-4;
    s+="<line x1='"+(q.p[0]+pp2[0]*(off-9)*h.side).toFixed(1)+"' y1='"+(q.p[1]+pp2[1]*(off-9)*h.side).toFixed(1)+"' x2='"+lx.toFixed(1)+"' y2='"+ly.toFixed(1)+"' stroke='"+C.rule+"' stroke-width='0.7'/>";
    s+="<text x='"+(lx+dx).toFixed(1)+"' y='"+(ly-1).toFixed(1)+"' font-size='9.5' "+FA+" font-weight='900' fill='"+C.text+"' text-anchor='"+anc+"'>"+h.lo+"</text>";
    s+="<text x='"+(lx+dx).toFixed(1)+"' y='"+(ly+7).toFixed(1)+"' font-size='5.6' "+FA+" font-weight='700' letter-spacing='0.13em' fill='"+C.muted+"' text-anchor='"+anc+"'>CARRY &#183; CLEAR "+h.hi+"</text>";
  }
  var gxs=G.green.map(function(p){return p[0];}), gys=G.green.map(function(p){return p[1];});
  var bx=Math.min(72,Math.max.apply(0,gxs)+9), by=Math.max(-494,(Math.max.apply(0,gys)+Math.min.apply(0,gys))/2);
  s+="<text x='"+bx.toFixed(1)+"' y='"+(by-7).toFixed(1)+"' font-size='8.4' "+FA+" font-weight='900' fill='"+C.text+"'>"+M.back+"</text>";
  s+="<text x='"+bx.toFixed(1)+"' y='"+(by+1.6).toFixed(1)+"' font-size='8.4' "+FA+" font-weight='900' fill='"+C.acc+"'>"+M.mid+"</text>";
  s+="<text x='"+bx.toFixed(1)+"' y='"+(by+10.2).toFixed(1)+"' font-size='8.4' "+FA+" font-weight='900' fill='"+C.text+"'>"+M.front+"</text>";
  s+="<text x='"+(bx+20).toFixed(1)+"' y='"+(by+1.6).toFixed(1)+"' font-size='5.2' "+FA+" font-weight='700' letter-spacing='0.12em' fill='"+C.muted+"'>B / C / F</text>";
  return s;
}
function renderLandformDay(el,H,meta){
  var S=fitPage(H), SUF='_'+el.id;
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var R=rng((meta.key||'c')+':'+H.hole+':landformday');
  var FIELD='#F1EFE5', T1='#E0E3CE', T2='#D2DABB', T3='#C3D0A8', FW='#B0C793', GN='#9DC176',
      SAND='#EBDDB4', INK='#14432A', MUT='#6E8570', RIM='#FFFFFF', ACID='#C7F24A';
  var defs="<defs>"
    +"<filter id='ldsh1"+SUF+"' x='-40%' y='-40%' width='180%' height='180%'><feDropShadow dx='1.5' dy='4' stdDeviation='4.5' flood-color='#5A6152' flood-opacity='0.32'/></filter>"
    +"<filter id='ldsh2"+SUF+"' x='-40%' y='-40%' width='180%' height='180%'><feDropShadow dx='1.2' dy='3' stdDeviation='3' flood-color='#5A6152' flood-opacity='0.30'/></filter>"
    +"<filter id='ldsh3"+SUF+"' x='-40%' y='-40%' width='180%' height='180%'><feDropShadow dx='0.9' dy='2' stdDeviation='1.8' flood-color='#5A6152' flood-opacity='0.28'/></filter>"
    +"<filter id='ldin"+SUF+"' x='-30%' y='-30%' width='160%' height='160%'><feDropShadow dx='0' dy='1.6' stdDeviation='2.2' flood-color='#3E5560' flood-opacity='0.45'/></filter>"
    +"<linearGradient id='ldw"+SUF+"' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#C3D9DF'/><stop offset='1' stop-color='#A9C4CD'/></linearGradient>"
    +"<radialGradient id='ldvig"+SUF+"' cx='0.5' cy='0.42' r='0.78'><stop offset='0.6' stop-color='#8A8B78' stop-opacity='0'/><stop offset='1' stop-color='#8A8B78' stop-opacity='0.16'/></radialGradient>"
    +"</defs>";
  var nm=stripName(meta.name||'THE COURSE');
  var s="<rect x='-155' y='-565' width='260' height='615' fill='"+FIELD+"'/>";
  function terrace(d, fill, filt){
    var o="<g transform='translate(-0.8,-1.1)'><path d='"+d+"' fill='"+RIM+"' opacity='0.6'/></g>";
    o+="<g filter='url(#"+filt+SUF+")'><path d='"+d+"' fill='"+fill+"'/></g>";
    o+="<path d='"+d+"' fill='none' stroke='#7E8C72' stroke-width='0.6' opacity='0.55'/>";
    return o;
  }
  function stepBand(pad, fill, filt){
    var d=smooth(corridor((G.fwStart!=null?Math.max(2,G.fwStart-(pad*26)):2), totalLen, function(a){return safeFw(a)+pad*9;}, null),true);
    return terrace(d, fill, filt);
  }
  s+=stepBand(3.4,T1,'ldsh1');
  s+=stepBand(2.4,T2,'ldsh2');
  s+=stepBand(1.5,T3,'ldsh2');
  if(G.fwStart!=null) s+=terrace(smooth(corridor(G.fwStart,totalLen-8,safeFw,null),true), FW, 'ldsh3');
  G.waters.forEach(function(w){
    var d=smooth(w,true);
    s+="<path d='"+d+"' fill='url(#ldw"+SUF+")'/>";
    s+="<g filter='url(#ldin"+SUF+")'><path d='"+smooth(inset(w.slice(0,-1),0.94),true)+"' fill='none' stroke='#7E9CA6' stroke-width='0.9' opacity='0.85'/></g>";
    s+="<path d='"+d+"' fill='none' stroke='#5F8894' stroke-width='0.7' opacity='0.7'/>";
  });
  G.bunkers.forEach(function(b){
    s+=terrace(smooth(b,true), SAND, 'ldsh3');
    s+="<path d='"+smooth(inset(b.slice(0,-1),0.55),true)+"' fill='none' stroke='#C2A970' stroke-width='0.7' opacity='0.8'/>";
  });
  s+=terrace(smooth(G.green,true), GN, 'ldsh3');
  s+="<path d='"+smooth(G.green,true)+"' fill='none' stroke='"+RIM+"' stroke-width='0.9' opacity='0.6'/>";
  var gp=lineAt(totalLen).p;
  s+="<circle cx='"+gp[0].toFixed(1)+"' cy='"+gp[1].toFixed(1)+"' r='4.8' fill='"+ACID+"' opacity='0.85'/>";
  s+="<circle cx='"+gp[0].toFixed(1)+"' cy='"+gp[1].toFixed(1)+"' r='2' fill='"+INK+"'/>";
  treeSpots(R).forEach(function(t){
    s+="<ellipse cx='"+(t[0]+t[2]*1.05).toFixed(1)+"' cy='"+(t[1]+2.6).toFixed(1)+"' rx='"+(t[2]*1.2).toFixed(1)+"' ry='"+(t[2]*0.38).toFixed(1)+"' fill='#5A6152' opacity='0.20'/>";
    s+="<circle cx='"+t[0].toFixed(1)+"' cy='"+t[1].toFixed(1)+"' r='"+(t[2]*0.72).toFixed(1)+"' fill='#9DB68C'/>";
    s+="<circle cx='"+(t[0]-t[2]*0.2).toFixed(1)+"' cy='"+(t[1]-t[2]*0.22).toFixed(1)+"' r='"+(t[2]*0.4).toFixed(1)+"' fill='#C0D3AC'/>";
    s+="<circle cx='"+(t[0]-t[2]*0.3).toFixed(1)+"' cy='"+(t[1]-t[2]*0.3).toFixed(1)+"' r='"+(t[2]*0.15).toFixed(1)+"' fill='"+RIM+"' opacity='0.8'/>";
  });
  G.tees.forEach(function(t){
    s+=terrace("M"+(t[0]-5).toFixed(1)+","+(t[1]-2.6).toFixed(1)+" h10 v5.2 h-10 Z", '#C9D3B8', 'ldsh3');
  });
  s+=lfMarksGen(H,S,{ rule:'rgba(20,67,42,0.42)', text:'#14432A', acc:'#2F6B45', muted:'#6E8570' });
  s+="<rect x='-155' y='-565' width='260' height='615' fill='url(#ldvig"+SUF+")'/>";
  s+="<text x='-140' y='-536' font-size='"+Math.max(6,Math.min(9,(150/Math.max(1,nm.length)-4.5)/0.62)).toFixed(1)+"' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='4.5' fill='"+INK+"'>"+nm+"</text>";
  s+="<text x='-140' y='-522' font-size='6' font-family='Archivo, sans-serif' font-weight='500' letter-spacing='3' fill='"+MUT+"'>YOINK CADDIE &#183; FROM THE SURVEY</text>";
  s+="<line x1='-140' y1='24' x2='-96' y2='24' stroke='"+MUT+"' stroke-width='0.7'/>";
  s+="<text x='-140' y='38' font-size='7' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='2.6' fill='"+INK+"'>N&#176; "+H.hole+" &#8212; PAR "+H.par+" &#8212; "+H.yards.mid+" YDS</text>";
  s+="<text x='96' y='38' font-size='6' font-family='Archivo, sans-serif' font-weight='500' letter-spacing='2.4' fill='"+MUT+"' text-anchor='end'>YOINK</text>";
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s;
}

/* ---------------- 7-9. THE CLEAR SET: Read, Zones, Ladder ---------------- */
var CX0=38, CGAP=16;
function clearColumn(items, tone){
  items = items.filter(function(x){return x;}).slice().sort(function(p,q){ return p.y-q.y; });
  for(var i=1;i<items.length;i++) if(items[i].y < items[i-1].y+CGAP) items[i].y = items[i-1].y+CGAP;
  for(var j=items.length-1;j>0;j--) if(items[j].y>26){ var d=items[j].y-26; for(var k=0;k<=j;k++) items[k].y-=d; break; }
  var o='', FA="font-family='Archivo, sans-serif'";
  items.forEach(function(it){
    if(it.ax!=null) o+="<path d='M"+it.ax.toFixed(1)+","+it.ay.toFixed(1)+" L"+(CX0-11)+","+it.ay.toFixed(1)
      +" L"+(CX0-4)+","+it.y.toFixed(1)+"' fill='none' stroke='"+tone.hair+"' stroke-width='0.6'/>";
    o+="<text x='"+CX0+"' y='"+(it.y+1).toFixed(1)+"' font-size='"+(it.fs||10.5)+"' "+FA+" font-weight='900' letter-spacing='-0.01em' fill='"+(it.color||tone.text)+"'>"+it.big+"</text>";
    if(it.small) o+="<text x='"+CX0+"' y='"+(it.y+8.2).toFixed(1)+"' font-size='5' "+FA+" font-weight='700' letter-spacing='0.05em' fill='"+(it.smallColor||tone.mut)+"'>"+it.small+"</text>";
  });
  return o;
}
function clearChrome(H,M,tone,rule){
  var FA="font-family='Archivo, sans-serif'";
  var s="<rect x='-155' y='-565' width='260' height='615' fill='"+tone.bg+"'/>";
  s+="<text x='-140' y='-518' font-size='34' "+FA+" font-weight='900' letter-spacing='-0.03em' fill='"+tone.text+"'>"+(H.hole<10?'0':'')+H.hole+"</text>";
  s+="<text x='-98' y='-532' font-size='8.5' "+FA+" font-weight='900' letter-spacing='0.14em' fill='"+tone.text+"'>PAR "+H.par+"</text>";
  s+="<text x='-98' y='-521' font-size='7.4' "+FA+" font-weight='700' letter-spacing='0.06em' fill='"+tone.mut+"'>"+M.total+" YARDS</text>";
  s+="<text x='98' y='-521' font-size='7' "+FA+" font-weight='700' letter-spacing='0.12em' fill='"+tone.mut+"' text-anchor='end'>"+rule+"</text>";
  s+="<line x1='-140' y1='-510' x2='98' y2='-510' stroke='"+tone.text+"' stroke-width='1.3'/>";
  s+="<line x1='"+(CX0-15)+"' y1='-494' x2='"+(CX0-15)+"' y2='6' stroke='"+tone.hair+"' stroke-width='0.7'/>";
  return s;
}
function clearFoot(H,tone,name){
  var FA="font-family='Archivo, sans-serif'";
  var s="<line x1='-140' y1='16' x2='98' y2='16' stroke='"+tone.hair+"' stroke-width='0.8'/>";
  s+="<text x='-140' y='30' font-size='6.4' "+FA+" font-weight='700' letter-spacing='0.08em' fill='"+tone.mut+"'>BACK "+H.yards.back+" &#183; MID "+H.yards.mid+" &#183; FWD "+H.yards.front+"</text>";
  s+="<text x='98' y='30' font-size='6.4' "+FA+" font-weight='900' letter-spacing='0.14em' fill='"+tone.text+"' text-anchor='end'>"+name+"</text>";
  return s;
}
function clearBase(safeFw, tone, noLine){
  var s='';
  s+="<path d='"+smooth(corridor(8,totalLen-4,function(a){return safeFw(a)+15;},null),true)+"' fill='"+tone.rough+"'/>";
  if(G.fwStart!=null) s+="<path d='"+smooth(corridor(G.fwStart,totalLen-8,safeFw,null),true)+"' fill='"+tone.turf+"' stroke='"+tone.hair+"' stroke-width='0.8'/>";
  G.waters.forEach(function(w){ s+="<path d='"+smooth(w,true)+"' fill='"+tone.water+"' stroke='"+tone.text+"' stroke-width='0.8'/>"; });
  G.bunkers.forEach(function(b){ s+="<path d='"+smooth(b,true)+"' fill='"+tone.sand+"' stroke='"+tone.text+"' stroke-width='0.8'/>"; });
  s+="<path d='"+smooth(G.green,true)+"' fill='"+tone.grn+"' stroke='"+tone.text+"' stroke-width='1.3'/>";
  G.tees.forEach(function(t){ s+="<rect x='"+(t[0]-2.6).toFixed(1)+"' y='"+(t[1]-1.6).toFixed(1)+"' width='5.2' height='3.2' fill='"+tone.text+"'/>"; });
  if(!noLine) s+="<path d='"+smooth(G.line,false)+"' fill='none' stroke='"+tone.text+"' stroke-width='0.9' stroke-dasharray='5 4'/>";
  return s;
}
var CTONE={ bg:'#FBFBF8', text:'#131614', mut:'#7A817B', hair:'#C9CDC6', acc:'#E0432C',
  rough:'#F1F0E6', turf:'#EAEEE5', water:'#DFE9EC', sand:'#F2E9D2', grn:'#DCE4D6' };
function greenCentroid(){ var c=[0,0]; G.green.forEach(function(p){c[0]+=p[0];c[1]+=p[1];}); return [c[0]/G.green.length,c[1]/G.green.length]; }

function renderRead(el,H,meta){
  var S=fitPage(H), M=measureH(H), T=CTONE;
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var s=clearChrome(H,M,T,'CARRY READ');
  var B=artBox(-140,-490,158,486);
  s+="<g transform='"+B.t+"' vector-effect='non-scaling-stroke'>"+clearBase(safeFw,T);
  for(var y=100;y<M.front-40;y+=50){
    var q=lineAt(y*S), w=safeFw(y*S)+7, pp=[q.d[1],-q.d[0]];
    var x1=q.p[0]-pp[0]*w, y1=q.p[1]-pp[1]*w;
    s+="<line x1='"+x1.toFixed(1)+"' y1='"+y1.toFixed(1)+"' x2='"+(q.p[0]+pp[0]*w).toFixed(1)+"' y2='"+(q.p[1]+pp[1]*w).toFixed(1)+"' stroke='"+T.mut+"' stroke-width='0.55' stroke-dasharray='2 2.4'/>";
    s+="<text x='"+(x1-3).toFixed(1)+"' y='"+(y1+2.4).toFixed(1)+"' font-size='6.4' font-family='Archivo, sans-serif' font-weight='900' fill='"+T.mut+"' text-anchor='end'>"+y+"</text>";
  }
  if(M.land!=null){ var lq=lineAt(M.land*S);
    s+="<circle cx='"+lq.p[0].toFixed(1)+"' cy='"+lq.p[1].toFixed(1)+"' r='11.5' fill='none' stroke='"+T.acc+"' stroke-width='1.3' stroke-dasharray='4 3'/>";
    s+="<circle cx='"+lq.p[0].toFixed(1)+"' cy='"+lq.p[1].toFixed(1)+"' r='1.6' fill='"+T.acc+"'/>"; }
  var pc=greenCentroid();
  s+="<circle cx='"+pc[0].toFixed(1)+"' cy='"+pc[1].toFixed(1)+"' r='2.4' fill='"+T.acc+"'/>";
  s+="</g>";
  var items=[], k=B.k, tx=B.t;
  function toPage(p){ var m=/translate\(([-\d.]+),([-\d.]+)\) scale\(([\d.]+)\)/.exec(tx);
    return [ +m[1]+p[0]*+m[3], +m[2]+p[1]*+m[3] ]; }
  M.carry.forEach(function(h){ var q=toPage(lineAt(((h.lo+h.hi)/2)*S).p);
    items.push({ y:q[1], ax:q[0], ay:q[1], big:''+h.lo,
      small:"CLR "+h.hi+" &#183; "+(h.kind==='water'?'WTR ':'SAND ')+(h.side>0?'R':'L') }); });
  if(M.land!=null){ var lp=toPage(lineAt(M.land*S).p);
    items.push({ y:lp[1], ax:lp[0]+10, ay:lp[1], big:''+M.land, color:T.acc, smallColor:T.acc,
      small:"IDEAL &#183; LVS "+(M.total-M.land) }); }
  var gp=toPage(pc);
  items.push({ y:gp[1], ax:gp[0]+8, ay:gp[1], big:M.mid+"<tspan font-size='5.6' font-weight='700' fill='"+T.mut+"'> CTR</tspan>",
    small:"GRN "+M.front+"F &#183; "+M.back+"B" });
  s+=clearColumn(items,T)+clearFoot(H,T,'THE READ');
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=s;
}

function renderZones(el,H,meta){
  var S=fitPage(H), M=measureH(H), T=CTONE;
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var s=clearChrome(H,M,T,'LANDING ZONES');
  var B=artBox(-140,-490,158,486);
  var m=/translate\(([-\d.]+),([-\d.]+)\) scale\(([\d.]+)\)/.exec(B.t);
  function toPage(p){ return [ +m[1]+p[0]*+m[3], +m[2]+p[1]*+m[3] ]; }
  s+="<g transform='"+B.t+"' vector-effect='non-scaling-stroke'>"+clearBase(safeFw,T,true);
  var zones=[];
  if(H.par===3){
    zones.push({a:Math.max(30,M.front-50), b:M.front, tag:'SHORT IS DEAD', verdict:'CARRY '+M.front, bad:true});
  } else {
    var stops=[], prev=Math.max(110, Math.round(H.fw_start||110));
    M.carry.forEach(function(h){
      if(h.lo>prev+16) stops.push({a:prev,b:h.lo,bad:false});
      stops.push({a:h.lo,b:h.hi,bad:true,h:h});
      prev=Math.max(prev,h.hi);
    });
    var end=Math.min(M.total-100, prev+95);
    if(end>prev+16) stops.push({a:prev,b:end,bad:false});
    stops=stops.filter(function(z){ return (z.b-z.a)>14; });
    if(stops.length>4){ var keep=stops.filter(function(z){return !z.bad;}), bad=stops.filter(function(z){return z.bad;});
      bad.sort(function(p,q){ return (q.b-q.a)-(p.b-p.a); });
      stops=keep.concat(bad.slice(0,Math.max(0,4-keep.length))).sort(function(p,q){ return p.a-q.a; }); }
    stops.forEach(function(z){
      var mid=Math.round((z.a+z.b)/2);
      zones.push({ a:z.a, b:z.b, bad:z.bad,
        tag: z.bad ? ((z.h.kind==='water'?'WATER ':'SAND ')+(z.h.side>0?'R':'L')) : 'LAND HERE',
        verdict: z.bad ? ('CARRY '+z.b) : ('LEAVES '+(M.total-mid)) });
    });
  }
  var items=[];
  zones.forEach(function(z){
    if(z.b<=z.a+4) return;
    var wf=function(a){ return safeFw(a)+3; };
    s+="<path d='"+smooth(corridor(z.a*S, z.b*S, wf, null), true)+"' fill='"+(z.bad?'rgba(224,67,44,0.11)':'rgba(19,22,20,0.06)')
      +"' stroke='"+(z.bad?T.acc:T.text)+"' stroke-width='"+(z.bad?0.9:1.2)+"'"+(z.bad?" stroke-dasharray='4 3'":"")+"/>";
    var q=toPage(lineAt(((z.a+z.b)/2)*S).p);
    items.push({ y:q[1], ax:q[0], ay:q[1], big:z.verdict, fs:z.bad?10.5:11.5,
      color:z.bad?T.acc:T.text, smallColor:z.bad?T.acc:T.mut,
      small:z.tag+" "+Math.round(z.a)+"&#8211;"+Math.round(z.b) });
  });
  s+="<path d='"+smooth(G.line,false)+"' fill='none' stroke='"+T.text+"' stroke-width='0.9' stroke-dasharray='5 4'/>";
  var pc=greenCentroid();
  s+="<circle cx='"+pc[0].toFixed(1)+"' cy='"+pc[1].toFixed(1)+"' r='2.4' fill='"+T.acc+"'/>";
  s+="</g>";
  var gp=toPage(pc);
  items.push({ y:gp[1], ax:gp[0]+8, ay:gp[1], big:M.mid+"<tspan font-size='5.6' font-weight='700' fill='"+T.mut+"'> CTR</tspan>",
    small:"GRN "+M.front+"F &#183; "+M.back+"B", color:T.acc });
  s+=clearColumn(items,T)+clearFoot(H,T,'ZONES');
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=s;
}

function renderLadder(el,H,meta){
  var S=fitPage(H), M=measureH(H), T=CTONE;
  var safeFw=(G.fwStart!=null)?fwWidth:function(a){return 13;};
  var s=clearChrome(H,M,T,'YARDAGE LADDER');
  var B=artBox(-104,-490,124,486);
  var m=/translate\(([-\d.]+),([-\d.]+)\) scale\(([\d.]+)\)/.exec(B.t);
  function toPage(p){ return [ +m[1]+p[0]*+m[3], +m[2]+p[1]*+m[3] ]; }
  s+="<g transform='"+B.t+"' vector-effect='non-scaling-stroke'>"+clearBase(safeFw,T);
  var pc=greenCentroid();
  s+="<circle cx='"+pc[0].toFixed(1)+"' cy='"+pc[1].toFixed(1)+"' r='2.4' fill='"+T.acc+"'/>";
  s+="</g>";
  var LX=-136, yTop=toPage(lineAt(totalLen).p)[1], yBot=toPage(lineAt(0).p)[1];
  s+="<line x1='"+LX+"' y1='"+yTop.toFixed(1)+"' x2='"+LX+"' y2='"+yBot.toFixed(1)+"' stroke='"+T.text+"' stroke-width='1.1'/>";
  for(var y=0;y<=M.total;y+=25){
    var yy=toPage(lineAt(Math.min(y,M.total)*S).p)[1], maj=(y%100===0);
    s+="<line x1='"+LX+"' y1='"+yy.toFixed(1)+"' x2='"+(LX+(maj?7:4))+"' y2='"+yy.toFixed(1)+"' stroke='"+(maj?T.text:T.hair)+"' stroke-width='"+(maj?1.1:0.7)+"'/>";
    if(maj) s+="<text x='"+(LX+10)+"' y='"+(yy+2.5).toFixed(1)+"' font-size='7' font-family='Archivo, sans-serif' font-weight='900' fill='"+T.text+"'>"+y+"</text>";
  }
  s+="<text x='"+LX+"' y='"+(yBot+13).toFixed(1)+"' font-size='5.8' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='0.14em' fill='"+T.mut+"'>FROM TEE</text>";
  var items=[];
  if(H.fw_start) items.push({ y:toPage(lineAt(H.fw_start*S).p)[1], big:''+Math.round(H.fw_start), small:'FAIRWAY BEGINS', fs:10 });
  M.carry.forEach(function(h){ var q=toPage(lineAt(h.lo*S).p);
    items.push({ y:q[1], ax:q[0], ay:q[1], big:h.lo+"<tspan font-size='6.4' fill='"+T.mut+"'>&#8211;"+h.hi+"</tspan>",
      small:(h.kind==='water'?'WTR ':'SAND ')+(h.side>0?'R':'L')+" &#183; CLR "+h.hi, fs:9.5 }); });
  if(M.land!=null){ var lq=toPage(lineAt(M.land*S).p);
    items.push({ y:lq[1], ax:lq[0], ay:lq[1], big:''+M.land, color:T.acc, smallColor:T.acc,
      small:'IDEAL &#183; LEAVES '+(M.total-M.land) }); }
  items.push({ y:toPage(lineAt(M.front*S).p)[1], big:''+M.front, small:'GREEN FRONT', fs:10 });
  items.push({ y:toPage(lineAt(M.back*S).p)[1]+12, big:''+M.back, small:'GREEN BACK', fs:9.5 });
  s+=clearColumn(items,T)+clearFoot(H,T,'THE LADDER');
  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=s;
}

// ---- style picker: injected into any Crown demo page ----
function boot(){
  var packsEl=document.getElementById('cpacks');
  if(!packsEl) return;
  var packs=JSON.parse(packsEl.textContent);
  var meta=window.CADDIE_COURSE||{};
  meta.n=packs.length;
  var byHole={}; packs.forEach(function(p){ byHole[p.hole]=p; });
  var arts=[].slice.call(document.querySelectorAll('svg.holeart')).map(function(el){
    var m=(el.getAttribute('aria-label')||'').match(/Hole (\d+)/);
    return m?{el:el, hole:+m[1], vb:el.getAttribute('viewBox'), html:el.innerHTML}:null;
  }).filter(Boolean);
  if(!arts.length) return;

  var css=".ykstyles{display:flex;gap:8px;align-items:center;margin:14px 0 2px;flex-wrap:wrap}"
    +".ykstyles span{font:700 10px Archivo,sans-serif;letter-spacing:.14em;color:var(--muted,#6D7770)}"
    +".ykchip{font:700 12px Archivo,sans-serif;border:1.5px solid var(--hair,#E3E3DC);background:var(--card,#fff);"
    +"color:var(--ink,#0C1710);border-radius:999px;padding:6px 14px;cursor:pointer}"
    +".ykchip.on{background:var(--forest,#14432A);border-color:var(--forest,#14432A);color:#F2F6EE}";
  var st=document.createElement('style'); st.textContent=css; document.head.appendChild(st);

  var bar=document.createElement('div'); bar.className='ykstyles';
  bar.innerHTML="<span>STYLE</span>";
  var defs=[['book','The Book'],['estate','Estate'],['landform','Landform'],['landformday','Landform Day'],['evening','Evening'],['surveyor','Surveyor'],['fieldnote','Field Note'],['instrument','Instrument'],['caddie','Caddie'],['fairway','Fairway'],['read','The Read'],['zones','Zones'],['ladder','The Ladder'],['crown','Gen 11']];
  var btns={};
  defs.forEach(function(d){
    var b=document.createElement('button'); b.className='ykchip'; b.textContent=d[1];
    b.onclick=function(){ apply(d[0]); };
    btns[d[0]]=b; bar.appendChild(b);
  });
  var mast=document.querySelector('.mast');
  (mast||document.body).appendChild(bar);

  function apply(mode){
    defs.forEach(function(d){ btns[d[0]].classList.toggle('on', d[0]===mode); });
    arts.forEach(function(a){
      var H=byHole[a.hole];
      if(mode==='book' && H){ renderBook(a.el, H, meta); }
      else if(mode==='estate' && H){ renderEstate(a.el, H, meta); }
      else if(mode==='landform' && H){ renderLandform(a.el, H, meta); }
      else if(mode==='evening' && H){ renderEvening(a.el, H, meta); }
      else if(mode==='landformday' && H){ renderLandformDay(a.el, H, meta); }
      else if(mode==='surveyor' && H){ renderSurveyor(a.el, H, meta); }
      else if(mode==='fieldnote' && H){ renderFieldNote(a.el, H, meta); }
      else if(mode==='instrument' && H){ renderInstrument(a.el, H, meta); }
      else if(mode==='caddie' && H){ renderCaddie(a.el, H, meta); }
      else if(mode==='fairway' && H){ renderFairway(a.el, H, meta); }
      else if(mode==='read' && H){ renderRead(a.el, H, meta); }
      else if(mode==='zones' && H){ renderZones(a.el, H, meta); }
      else if(mode==='ladder' && H){ renderLadder(a.el, H, meta); }
      else { a.el.setAttribute('viewBox', a.vb); a.el.innerHTML=a.html; }
    });
    try{ localStorage.setItem('caddie-style', mode); }catch(e){}
  }
  var want='book';
  try{ want=localStorage.getItem('caddie-style')||'book'; }catch(e){}
  var m=(location.hash+' '+location.search).match(/style=(book|crown|estate|landformday|landform|evening|surveyor|fieldnote|instrument|caddie|fairway|read|zones|ladder)/);
  if(m) want=m[1];
  apply(({book:1,crown:1,estate:1,landform:1,landformday:1,evening:1,surveyor:1,fieldnote:1,instrument:1,caddie:1,fairway:1,read:1,zones:1,ladder:1})[want]?want:'book');
}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', boot); else boot();

})();
