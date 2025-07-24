import React from 'react';


interface FAQItem {
    question: string;
    answer: string;
  }

const FAQSection: React.FC = () => {
    const faqs: FAQItem[] = [
      {
        question: "How do I post everywhere at once?",
        answer: "Just pick your platforms, set your schedule, and your videos go live across YouTube, TikTok, and Instagram—no extra steps or logins needed."
      },
      {
        question: "Which video files can I upload?",
        answer: "Most popular video and audio formats are good to go. Upload your file and we'll handle the rest, optimizing for each platform automatically."
      },
      {
        question: "Can I switch between different accounts?",
        answer: "Yes! Connect all your accounts, manage multiple brands or clients, and keep everything organized in one easy dashboard."
      },
      {
        question: "How is my data kept safe?",
        answer: "Your uploads and info are encrypted and protected. Only you can access your content, and all platform connections use secure authentication."
      }
    ];
  
    return (
      <section className="bg-[#17183D]py-20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <span className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
              Quick answers, no jargon
            </span>
            <h2 className="text-4xl font-bold text-white mt-4 mb-6">
              YOUR TOP QUESTIONS, EXPLAINED SIMPLY
            </h2>
            <p className="text-xl text-gray-400">
              Wondering how it all fits together? We've gathered the most common questions from creators like you—so you can get started with confidence, minus the tech-speak.
            </p>
          </div>
  
          <div className="space-y-8">
            {faqs.map((faq, index) => (
              <div key={index} className="border-b border-gray-200 pb-8">
                <div className="grid md:grid-cols-2 gap-6">
                  <h3 className="text-xl font-bold text-white">
                    {faq.question}
                  </h3>
                  <p className="text-gray-300">
                    {faq.answer}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  };

  export default FAQSection;